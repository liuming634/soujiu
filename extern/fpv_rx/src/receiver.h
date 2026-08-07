#pragma once
#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <fstream>
#include <memory>
#include <mutex>
#include <queue>
#include <string>
#include <thread>
#include <vector>

#ifdef _WIN32
#define NOMINMAX
#define _WINSOCKAPI_
#include <winsock2.h>
#include <ws2tcpip.h>
using socket_t = SOCKET;
#define INVALID_SOCKET_T INVALID_SOCKET
#define SOCKET_CLOSE closesocket
#define SOCKET_ERRNO WSAGetLastError()
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
using socket_t = int;
#define INVALID_SOCKET_T (-1)
#define SOCKET_CLOSE ::close
#define SOCKET_ERRNO errno
#endif

#include <libusb.h>

extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libswscale/swscale.h>
}

#include "Rtl8812aDevice.h"
#include "SelectedChannel.h"
#include "WFBDefine.h"
#include "logger.h"

struct FrameData {
    std::string codec;
    std::vector<uint8_t> data;
    int width = 0;
    int height = 0;
    bool is_keyframe = false;
    bool valid = false;
};

class Aggregator;

class FpvReceiver {
public:
    FpvReceiver();
    ~FpvReceiver();

    bool start(const std::string &vid_pid, uint8_t channel,
               int channel_width, const std::string &key_path,
               uint32_t link_id = 7669206,
               const std::string &codec = "h265",
               int video_width = 1280, int video_height = 720,
               int fps = 120);
    void stop();
    FrameData recv(int timeout_ms);
    bool connected() const { return connected_; }

private:
    void usb_worker(const std::string &vid_pid, uint8_t channel,
                    int channel_width);
    void on_wifi_frame(const Packet &pkt);
    void on_rtp_data(uint8_t *payload, uint16_t packet_size);
    void decode_loop(int pt, const std::string &codec_name);
    int get_free_port();
    std::string build_sdp(int port, int pt, const std::string &codec);
    bool is_h264(const uint8_t *data);

    libusb_context *ctx = nullptr;
    libusb_device_handle *dev_handle = nullptr;
    std::shared_ptr<std::thread> worker;
    std::unique_ptr<Rtl8812aDevice> rtl_device;
    std::string key_path_;
    Logger_t logger_;

    std::queue<FrameData> frame_queue_;
    std::mutex queue_mtx_;
    std::condition_variable queue_cv_;

    std::unique_ptr<Aggregator> aggregator_;
    uint32_t link_id_;
    uint32_t video_channel_id_;

    uint16_t _last_rtp_seq = 0;
    bool _rtp_seq_init = false;
    bool _drop_frame = false;
    std::atomic<bool> flush_decoder_{false};

    std::atomic<bool> connected_{false};

    socket_t send_fd_ = INVALID_SOCKET_T;
    int player_port_ = 0;
    std::atomic<bool> playing_{false};
    int codec_pt_ = 96;
    std::string codec_name_;
    std::string config_codec_;
    int config_width_ = 1280;
    int config_height_ = 720;
    int config_fps_ = 120;

    std::shared_ptr<std::thread> decode_thread_;
    std::atomic<bool> decode_stop_{false};
    std::mutex fmt_ctx_mtx_;
    AVFormatContext *fmt_ctx_ = nullptr;
};
