#include "receiver.h"
#include "FrameParser.h"
#include "Rtp.h"
#include "RxFrame.h"
#include "WFBProcessor.h"
#include "WiFiDriver.h"

#include <cstdio>
#include <cstring>
#include <iostream>
#include <sstream>

static int frame_count = 0;
static int last_log_time = 0;

static inline uint16_t read_u16_be(const uint8_t *p) {
    return (uint16_t)((p[0] << 8) | p[1]);
}

static inline uint32_t read_u32_be(const uint8_t *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

// ─── Constructor / Destructor ───

FpvReceiver::FpvReceiver()
    : logger_(std::make_shared<Logger>()) {
#ifdef _WIN32
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        logger_->error("WSAStartup failed");
    }
#endif
    send_fd_ = socket(AF_INET, SOCK_DGRAM, 0);
    if (send_fd_ == INVALID_SOCKET_T) {
        logger_->error("socket creation failed");
    }
}

FpvReceiver::~FpvReceiver() {
    stop();
    if (send_fd_ != INVALID_SOCKET_T) {
        SOCKET_CLOSE(send_fd_);
        send_fd_ = INVALID_SOCKET_T;
    }
#ifdef _WIN32
    WSACleanup();
#endif
}

// ─── Start / Stop ───

bool FpvReceiver::start(const std::string &vid_pid, uint8_t channel,
                         int channel_width, const std::string &key_path,
                         uint32_t link_id,
                         const std::string &codec,
                         int video_width, int video_height, int fps) {
    if (worker) return false;
    playing_ = false;
    decode_stop_ = false;
    player_port_ = 0;
    codec_name_.clear();
    codec_pt_ = 96;
    _rtp_seq_init = false;
    _drop_frame = false;
    config_codec_ = codec;
    config_width_ = video_width;
    config_height_ = video_height;
    config_fps_ = fps;
    link_id_ = link_id;
    video_channel_id_ = (link_id_ << 8) + 0;
    key_path_ = key_path;
    worker = std::make_shared<std::thread>([this, vid_pid, channel, channel_width]() {
        usb_worker(vid_pid, channel, channel_width);
    });
    return true;
}

void FpvReceiver::stop() {
    // Unblock FFmpeg av_read_frame so decode thread can exit
    {
        std::lock_guard<std::mutex> lock(fmt_ctx_mtx_);
        if (fmt_ctx_) {
            fmt_ctx_->interrupt_callback.callback = [](void *) { return 1; };
        }
    }
    decode_stop_ = true;

    if (rtl_device) {
        rtl_device->should_stop = true;
    }
    if (worker && worker->joinable()) {
        worker->join();
    }
    if (decode_thread_ && decode_thread_->joinable()) {
        decode_thread_->join();
        decode_thread_.reset();
    }

    aggregator_.reset();
    rtl_device.reset();
    connected_ = false;
    playing_ = false;
    player_port_ = 0;
    codec_name_.clear();
    _rtp_seq_init = false;
    _drop_frame = false;
}

// ─── USB worker (unchanged structure) ───

void FpvReceiver::usb_worker(const std::string &vid_pid, uint8_t channel,
                              int channel_width) {
    std::istringstream iss(vid_pid);
    unsigned int vid, pid;
    char sep;
    iss >> std::hex >> vid >> sep >> pid;

    libusb_init(&ctx);
    dev_handle = libusb_open_device_with_vid_pid(ctx, vid, pid);
    if (!dev_handle) {
        logger_->error("Device %04x:%04x not found", vid, pid);
        libusb_exit(ctx);
        ctx = nullptr;
        return;
    }

    int kd_active = libusb_kernel_driver_active(dev_handle, 0);
    if (kd_active == 1) {
        libusb_detach_kernel_driver(dev_handle, 0);
    } else if (kd_active < 0 && kd_active != LIBUSB_ERROR_NOT_SUPPORTED) {
        logger_->error("kernel_driver_active failed: %d", kd_active);
    }
    if (libusb_claim_interface(dev_handle, 0) < 0) {
        libusb_close(dev_handle);
        libusb_exit(ctx);
        dev_handle = nullptr;
        ctx = nullptr;
        return;
    }

    WiFiDriver wifi_driver(logger_);
    try {
        rtl_device = wifi_driver.CreateRtlDevice(dev_handle);
        connected_ = true;
        rtl_device->Init(
            [this](const Packet &p) { on_wifi_frame(p); },
            SelectedChannel{
                .Channel = channel,
                .ChannelOffset = 0,
                .ChannelWidth = static_cast<ChannelWidth_t>(channel_width)});
    } catch (const std::runtime_error &e) {
        logger_->error("Init error: %s", e.what());
        connected_ = false;
    } catch (...) {
        connected_ = false;
    }

    libusb_release_interface(dev_handle, 0);
    libusb_close(dev_handle);
    libusb_exit(ctx);
    dev_handle = nullptr;
    ctx = nullptr;
}

// ─── WiFi frame handler ───

void FpvReceiver::on_wifi_frame(const Packet &pkt) {
    if (!aggregator_) {
        try {
            aggregator_ = std::make_unique<Aggregator>(
                key_path_.c_str(), 0, video_channel_id_,
                [this](uint8_t *payload, uint16_t size) {
                    on_rtp_data(payload, size);
                });
            logger_->info("Aggregator created with key: %s", key_path_.c_str());
        } catch (const std::exception &e) {
            logger_->error("Aggregator init failed: %s", e.what());
            return;
        } catch (...) {
            logger_->error("Aggregator init failed (unknown error)");
            return;
        }
    }

    RxFrame frame(std::span<const uint8_t>(pkt.Data));
    if (!frame.IsValidWfbFrame()) {
        if (frame_count < 10) {
            uint8_t b0 = pkt.Data.size() > 0 ? pkt.Data[0] : 0;
            uint8_t b1 = pkt.Data.size() > 1 ? pkt.Data[1] : 0;
            uint8_t b10 = pkt.Data.size() > 10 ? pkt.Data[10] : 0;
            uint8_t b15 = pkt.Data.size() > 15 ? pkt.Data[15] : 0;
            uint8_t b16 = pkt.Data.size() > 16 ? pkt.Data[16] : 0;
            uint8_t b21 = pkt.Data.size() > 21 ? pkt.Data[21] : 0;
            logger_->info("INVALID frame: fc=0x%02x%02x b10=%02x b15=%02x b16=%02x b21=%02x size=%d",
                b1, b0, b10, b15, b16, b21, (int)pkt.Data.size());
        }
        return;
    }

    logger_->info("WFB frame MATCHED! size=%d", (int)pkt.Data.size());

    static int8_t rssi[4] = {1, 1, 1, 1};
    static uint8_t antenna[4] = {1, 1, 1, 1};

    size_t payload_size = pkt.Data.size();
    if (payload_size <= sizeof(ieee80211_header) + 4) return;
    aggregator_->process_packet(
        pkt.Data.data() + sizeof(ieee80211_header),
        payload_size - sizeof(ieee80211_header) - 4,
        0, antenna, rssi);
}

// ─── Codec detection ───

#define GET_H264_NAL_UNIT_TYPE(buffer_ptr) (buffer_ptr[0] & 0x1F)

bool FpvReceiver::is_h264(const uint8_t *data) {
    auto nal_type = GET_H264_NAL_UNIT_TYPE(data);
    return nal_type == 24 || nal_type == 28; // STAP-A or FU-A
}

// ─── RTP handler: forward to local UDP + start decode thread ───

void FpvReceiver::on_rtp_data(uint8_t *payload, uint16_t packet_size) {
    if (rtl_device && rtl_device->should_stop) return;
    if (packet_size < 12) return;

    auto *rtp = reinterpret_cast<RtpHeader *>(payload);
    logger_->info(">>> on_rtp_data: size=%d seq=%d mark=%d playing=%d codec='%s'",
                  (int)packet_size, ntohs(rtp->seq), (int)rtp->mark,
                  (int)playing_, codec_name_.c_str());

    if (!playing_) {
        playing_ = true;
        codec_name_ = (config_codec_ == "h264") ? "H264" : "H265";
        codec_pt_ = rtp->pt;
        logger_->info("=== FIRST RTP PACKET: codec=%s pt=%d width=%dx%d fps=%d ===",
                      codec_name_.c_str(), (int)codec_pt_,
                      config_width_, config_height_, config_fps_);

        // Start decode thread FIRST, it will open UDP socket and get port
        player_port_ = 0;
        decode_stop_ = false;
        try {
            decode_thread_ = std::make_shared<std::thread>(
                &FpvReceiver::decode_loop, this, codec_pt_, codec_name_);
            logger_->info("Decode thread launched, waiting for UDP port...");
        } catch (const std::exception &e) {
            logger_->error("Failed to create decode thread: %s", e.what());
            playing_ = false;
            return;
        }
    }

    // Wait for decode thread to open UDP socket and signal port
    if (player_port_ == 0) {
        std::unique_lock<std::mutex> lock(queue_mtx_);
        queue_cv_.wait_for(lock, std::chrono::seconds(10),
                           [this] { return player_port_ > 0 || decode_stop_; });
        if (player_port_ == 0) {
            logger_->error("Timed out waiting for decode thread UDP port");
            return;
        }
        logger_->info("UDP port ready: %d", player_port_);
    }

    // ── RTP 丢帧检测：seq 不连续则抛弃残帧，避免 FFmpeg 卡在残缺帧上 ──
    uint16_t seq = ntohs(rtp->seq);
    if (!_rtp_seq_init) {
        _rtp_seq_init = true;
        _last_rtp_seq = seq;
        _drop_frame = false;
    } else {
        uint16_t gap = (seq - _last_rtp_seq) & 0xFFFF;
        _last_rtp_seq = seq;
        if (gap > 1) {
            _drop_frame = true;  // 无论 mark 是什么，整帧丢弃
            flush_decoder_ = true;  // 丢包后重置解码器参考链
        }
    }

    if (_drop_frame) {
        if (rtp->mark) {
            _drop_frame = false;  // 残帧结束，下一帧放行
        }
        return;  // 抛弃此包，不给 FFmpeg
    }

    sockaddr_in server_addr{};
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons((uint16_t)player_port_);
    server_addr.sin_addr.s_addr = inet_addr("127.0.0.1");

    int sent = sendto(send_fd_, reinterpret_cast<const char *>(payload), packet_size, 0,
           (sockaddr *)&server_addr, sizeof(server_addr));
    if (sent != (int)packet_size) {
        logger_->warn("sendto sent %d of %d bytes", sent, (int)packet_size);
    }
}

// ─── Free port allocation ───

int FpvReceiver::get_free_port() {
    socket_t tmp = socket(AF_INET, SOCK_DGRAM, 0);
    if (tmp == INVALID_SOCKET_T) {
        logger_->warn("get_free_port: socket failed, using 5600");
        return 5600;
    }

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = inet_addr("127.0.0.1");
    addr.sin_port = 0;

    if (bind(tmp, (sockaddr *)&addr, sizeof(addr)) < 0) {
        logger_->warn("get_free_port: bind failed, using 5600");
        SOCKET_CLOSE(tmp);
        return 5600;
    }

#ifdef _WIN32
    int namelen = sizeof(addr);
#else
    socklen_t namelen = sizeof(addr);
#endif
    if (getsockname(tmp, (sockaddr *)&addr, &namelen) < 0) {
        logger_->warn("get_free_port: getsockname failed, using 5600");
        SOCKET_CLOSE(tmp);
        return 5600;
    }

    int port = ntohs(addr.sin_port);
    SOCKET_CLOSE(tmp);
    logger_->info("get_free_port: allocated port %d", port);
    return port;
}

// ─── SDP builder ───

std::string FpvReceiver::build_sdp(int port, int pt, const std::string &codec) {
    std::stringstream ss;
    ss << "v=0\n";
    ss << "o=- 0 0 IN IP4 127.0.0.1\n";
    ss << "s=No Name\n";
    ss << "c=IN IP4 127.0.0.1\n";
    ss << "t=0 0\n";
    ss << "m=video " << port << " RTP/AVP " << pt << "\n";
    ss << "a=rtpmap:" << pt << " " << codec << "/90000\n";
    return ss.str();
}

// ─── FFmpeg RTP decode loop ───

void FpvReceiver::decode_loop(int pt, const std::string &codec_name) {
    logger_->info("[DECODE] decode_loop started: pt=%d codec=%s", pt, codec_name.c_str());

    // Try a range of high ports; keep window between SOCKET_CLOSE and avformat_open_input tiny
    int actual_port = 0;
    socket_t tmp_sock = INVALID_SOCKET_T;
    for (int port = 5600; port <= 5700; port++) {
        socket_t s = socket(AF_INET, SOCK_DGRAM, 0);
        if (s == INVALID_SOCKET_T) continue;
        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_addr.s_addr = inet_addr("127.0.0.1");
        addr.sin_port = htons((uint16_t)port);
        if (bind(s, (sockaddr*)&addr, sizeof(addr)) == 0) {
            actual_port = port;
            tmp_sock = s;
            break;
        }
        SOCKET_CLOSE(s);
    }
    if (actual_port == 0) {
        logger_->error("[DECODE] No free port found in range 5600-5700");
        return;
    }
    logger_->info("[DECODE] Found free port: %d", actual_port);

    // Write SDP file
    std::string sdp_content = build_sdp(actual_port, pt, codec_name);
    std::string sdp_path = "fpv_rx_sdp.sdp";
    {
        std::ofstream ofs(sdp_path);
        if (!ofs) {
            logger_->error("[DECODE] Failed to write SDP file");
            SOCKET_CLOSE(tmp_sock);
            return;
        }
        ofs << sdp_content;
        ofs.close();
    }
    logger_->info("[DECODE] SDP written (port %d):\n%s", actual_port, sdp_content.c_str());

    // Release our temporary socket
    SOCKET_CLOSE(tmp_sock);

    // IMMEDIATELY call avformat_open_input to minimise port race
    // Pre-allocate context and set interrupt BEFORE open_input to prevent deadlock in stop()
    AVFormatContext *fmt_ctx = avformat_alloc_context();
    if (!fmt_ctx) {
        logger_->error("[DECODE] avformat_alloc_context FAILED");
        return;
    }
    {
        std::lock_guard<std::mutex> lock(fmt_ctx_mtx_);
        fmt_ctx_ = fmt_ctx;
    }
    // 中断回调：只查 decode_stop_（stop() 设此标志即可打断 avformat_open_input）
    fmt_ctx->interrupt_callback.callback = [](void *opaque) -> int {
        return *(static_cast<std::atomic<bool>*>(opaque)) ? 1 : 0;
    };
    fmt_ctx->interrupt_callback.opaque = &decode_stop_;

    AVDictionary *opts = nullptr;
    av_dict_set(&opts, "protocol_whitelist", "file,udp,rtp,tcp", 0);
    av_dict_set(&opts, "probesize", "10240", 0);         // 10KB 探测（默认1MB）
    av_dict_set(&opts, "analyzeduration", "300000", 0);   // 300ms 分析（默认5s）

    logger_->info("[DECODE] Calling avformat_open_input...");
    int ret = avformat_open_input(&fmt_ctx, sdp_path.c_str(), nullptr, &opts);
    av_dict_free(&opts);
    if (ret < 0) {
        char errbuf[256] = {};
        av_strerror(ret, errbuf, sizeof(errbuf));
        logger_->error("[DECODE] avformat_open_input FAILED: %s", errbuf);
        {
            std::lock_guard<std::mutex> lock(fmt_ctx_mtx_);
            fmt_ctx_ = nullptr;
        }
        avformat_close_input(&fmt_ctx);
        return;
    }
    logger_->info("[DECODE] avformat_open_input SUCCESS");

    // Signal port to on_rtp_data — FFmpeg 已在监听，可以发 UDP 了
    {
        std::lock_guard<std::mutex> lock(queue_mtx_);
        player_port_ = actual_port;
    }
    queue_cv_.notify_one();

    logger_->info("[DECODE] Calling avformat_find_stream_info...");
    ret = avformat_find_stream_info(fmt_ctx, nullptr);
    if (ret < 0) {
        logger_->error("[DECODE] avformat_find_stream_info FAILED");
        avformat_close_input(&fmt_ctx);
        {
            std::lock_guard<std::mutex> lock(fmt_ctx_mtx_);
            fmt_ctx_ = nullptr;
        }
        return;
    }
    logger_->info("[DECODE] avformat_find_stream_info SUCCESS (%d streams)", fmt_ctx->nb_streams);

    // 中断回调：只查 decode_stop_（stop() 设此标志即可打断 av_read_frame）
    fmt_ctx->interrupt_callback.callback = [](void *opaque) -> int {
        return *(static_cast<std::atomic<bool>*>(opaque)) ? 1 : 0;
    };
    fmt_ctx->interrupt_callback.opaque = &decode_stop_;

    // Store for stop() to access (interrupt callback)
    {
        std::lock_guard<std::mutex> lock(fmt_ctx_mtx_);
        fmt_ctx_ = fmt_ctx;
    }

    // Find video stream
    int video_stream = -1;
    for (unsigned int i = 0; i < fmt_ctx->nb_streams; i++) {
        logger_->info("[DECODE] Stream %d: type=%d codec=%s",
                      i, fmt_ctx->streams[i]->codecpar->codec_type,
                      avcodec_get_name(fmt_ctx->streams[i]->codecpar->codec_id));
        if (fmt_ctx->streams[i]->codecpar->codec_type == AVMEDIA_TYPE_VIDEO) {
            video_stream = (int)i;
            break;
        }
    }
    if (video_stream < 0) {
        logger_->error("[DECODE] No video stream found in input");
        avformat_close_input(&fmt_ctx);
        return;
    }
    logger_->info("[DECODE] Found video stream %d", video_stream);

    // Init decoder
    const AVCodec *codec = avcodec_find_decoder(
        fmt_ctx->streams[video_stream]->codecpar->codec_id);
    if (!codec) {
        logger_->error("[DECODE] avcodec_find_decoder FAILED for codec_id=%d",
                       fmt_ctx->streams[video_stream]->codecpar->codec_id);
        avformat_close_input(&fmt_ctx);
        return;
    }
    logger_->info("[DECODE] Found decoder: %s", codec->name);

    AVCodecContext *codec_ctx = avcodec_alloc_context3(codec);
    if (!codec_ctx) {
        logger_->error("[DECODE] avcodec_alloc_context3 FAILED");
        avformat_close_input(&fmt_ctx);
        return;
    }

    ret = avcodec_parameters_to_context(codec_ctx,
              fmt_ctx->streams[video_stream]->codecpar);
    if (ret < 0) {
        logger_->error("[DECODE] avcodec_parameters_to_context FAILED");
        avcodec_free_context(&codec_ctx);
        avformat_close_input(&fmt_ctx);
        return;
    }

    logger_->info("[DECODE] Calling avcodec_open2...");
    ret = avcodec_open2(codec_ctx, codec, nullptr);
    if (ret < 0) {
        char errbuf[256] = {};
        av_strerror(ret, errbuf, sizeof(errbuf));
        logger_->error("[DECODE] avcodec_open2 FAILED: %s", errbuf);
        avcodec_free_context(&codec_ctx);
        avformat_close_input(&fmt_ctx);
        return;
    }

    logger_->info("[DECODE] FFmpeg RTP decoder initialized (%s, %dx%d)",
                  codec_name.c_str(), codec_ctx->width, codec_ctx->height);

    AVFrame *frame = av_frame_alloc();
    AVPacket *pkt = av_packet_alloc();
    SwsContext *sws_ctx = nullptr;
    int frame_count = 0;
    bool waiting_keyframe = false;

    // Decode loop
    logger_->info("[DECODE] Entering decode loop");
    while (!decode_stop_) {
        // 丢包后 flush 解码器 + 进入关键帧等待模式
        if (flush_decoder_.exchange(false)) {
            avcodec_flush_buffers(codec_ctx);
            waiting_keyframe = true;
            logger_->info("[DECODE] Decoder flushed, waiting for clean keyframe...");
        }
        ret = av_read_frame(fmt_ctx, pkt);
        if (ret < 0) {
            if (ret == AVERROR_EOF) {
                logger_->info("[DECODE] av_read_frame: EOF");
                break;
            }
            if (decode_stop_) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
            continue;
        }

        if (pkt->stream_index == video_stream) {
            frame_count++;
            logger_->info("[DECODE] av_read_frame OK (#%d): size=%d flags=%d",
                          frame_count, pkt->size, pkt->flags);

            int send_ret = avcodec_send_packet(codec_ctx, pkt);
            if (send_ret < 0) {
                char errbuf[256] = {};
                av_strerror(send_ret, errbuf, sizeof(errbuf));
                logger_->warn("[DECODE] avcodec_send_packet: %s", errbuf);
            } else {
                while (true) {
                    ret = avcodec_receive_frame(codec_ctx, frame);
                    if (ret == 0) {
                        int w = frame->width;
                        int h = frame->height;
                        logger_->info("[DECODE] >>> FRAME DECODED: %dx%d pix_fmt=%d",
                                      w, h, frame->format);
                        if (w <= 0 || h <= 0) continue;

                        // 关键帧门控：flush 后丢弃所有非关键帧，防止参考链污染导致花屏
                        if (waiting_keyframe) {
#ifdef AV_FRAME_FLAG_KEY
                            bool is_key = (frame->flags & AV_FRAME_FLAG_KEY) != 0;
#else
                            bool is_key = frame->key_frame != 0;
#endif
                            if (!is_key) {
                                logger_->info("[DECODE] Skipping non-keyframe %dx%d (waiting for clean keyframe)",
                                              w, h);
                                continue;
                            }
                            waiting_keyframe = false;
                            logger_->info("[DECODE] Clean keyframe recovered, resuming display");
                        }

                        sws_ctx = sws_getCachedContext(sws_ctx,
                            w, h, (AVPixelFormat)frame->format,
                            w, h, AV_PIX_FMT_BGR24,
                            SWS_BILINEAR, nullptr, nullptr, nullptr);
                        if (!sws_ctx) {
                            logger_->error("[DECODE] sws_getCachedContext FAILED");
                            continue;
                        }

                        int bgr_stride = w * 3;
                        std::vector<uint8_t> bgr((size_t)bgr_stride * h);
                        uint8_t *dst[1] = { bgr.data() };
                        int dst_stride[1] = { bgr_stride };

                        sws_scale(sws_ctx, frame->data, frame->linesize,
                                  0, h, dst, dst_stride);

                        FrameData fd;
                        fd.codec = codec_name;
                        fd.data = std::move(bgr);
                        fd.width = w;
                        fd.height = h;
                        fd.is_keyframe = false;
                        fd.valid = true;

                        logger_->info("[DECODE] >>> PUSHING to queue: %dx%d data=%d bytes",
                                      w, h, (int)fd.data.size());

                        {
                            std::lock_guard<std::mutex> lock(queue_mtx_);
                            if (frame_queue_.size() > 3) {
                                frame_queue_.pop();
                            }
                            frame_queue_.push(std::move(fd));
                        }
                        queue_cv_.notify_one();
                        logger_->info("[DECODE] >>> FRAME PUSHED to Python queue");
                    } else if (ret == AVERROR(EAGAIN)) {
                        logger_->info("[DECODE] avcodec_receive_frame: EAGAIN (need more data)");
                        break;
                    } else {
                        char errbuf[256] = {};
                        av_strerror(ret, errbuf, sizeof(errbuf));
                        logger_->warn("[DECODE] avcodec_receive_frame error: %s", errbuf);
                        break;
                    }
                }
            }
        }
        av_packet_unref(pkt);
    }

    logger_->info("[DECODE] Decode loop exited, total frames processed: %d", frame_count);

    if (sws_ctx) sws_freeContext(sws_ctx);
    av_frame_free(&frame);
    av_packet_free(&pkt);
    avcodec_free_context(&codec_ctx);
    avformat_close_input(&fmt_ctx);

    {
        std::lock_guard<std::mutex> lock(fmt_ctx_mtx_);
        fmt_ctx_ = nullptr;
    }

    // Clean up SDP file
    std::remove(sdp_path.c_str());

    logger_->info("Decode loop exited");
}

// ─── Frame receive (Python interface) ───

FrameData FpvReceiver::recv(int timeout_ms) {
    if (timeout_ms < 0) timeout_ms = 0;
    if (timeout_ms > 60000) timeout_ms = 60000;
    std::unique_lock<std::mutex> lock(queue_mtx_);
    if (queue_cv_.wait_for(lock, std::chrono::milliseconds(timeout_ms),
                            [this] { return !frame_queue_.empty(); })) {
        // 排空队列，只取最新帧（实时性优先，跳过积压的旧帧）
        while (frame_queue_.size() > 1) {
            frame_queue_.pop();
        }
        FrameData fd = std::move(frame_queue_.front());
        frame_queue_.pop();
        return fd;
    }
    return FrameData{};
}
