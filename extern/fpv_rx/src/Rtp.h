#ifndef FPV_WFB_RTP_H
#define FPV_WFB_RTP_H

#include <sstream>
#include <cstdint>
#include <cstddef>
#include <string>
#ifdef _WIN32
#include <stdlib.h>
#define ntohs(x) _byteswap_ushort(x)
#define ntohl(x) _byteswap_ulong(x)
#else
#include <arpa/inet.h>
#endif

#ifndef PACKED
#if defined(_WIN32)
#define PACKED
#pragma pack(push, 1)
#else
#define PACKED __attribute__((packed))
#endif
#endif

class RtpHeader {
public:
#if defined(__BYTE_ORDER) && __BYTE_ORDER == __BIG_ENDIAN || defined(_WIN32) && REG_DWORD == REG_DWORD_BIG_ENDIAN
    uint32_t version : 2;
    uint32_t padding : 1;
    uint32_t ext : 1;
    uint32_t csrc : 4;
    uint32_t mark : 1;
    uint32_t pt : 7;
#else
    uint32_t csrc : 4;
    uint32_t ext : 1;
    uint32_t padding : 1;
    uint32_t version : 2;
    uint32_t pt : 7;
    uint32_t mark : 1;
#endif
    uint32_t seq : 16;
    uint32_t stamp;
    uint32_t ssrc;
    uint8_t payload;

public:
#define AV_RB16(x) ((((const uint8_t *)(x))[0] << 8) | ((const uint8_t *)(x))[1])

    size_t getCsrcSize() const { return csrc << 2; }

    uint8_t *getCsrcData() {
        if (!csrc) return nullptr;
        return &payload;
    }

    size_t getExtSize() const {
        if (!ext) return 0;
        auto ext_ptr = &payload + getCsrcSize();
        return AV_RB16(ext_ptr + 2) << 2;
    }

    uint16_t getExtReserved() const {
        if (!ext) return 0;
        auto ext_ptr = &payload + getCsrcSize();
        return AV_RB16(ext_ptr);
    }

    uint8_t *getExtData() {
        if (!ext) return nullptr;
        auto ext_ptr = &payload + getCsrcSize();
        return ext_ptr + 4;
    }

    size_t getPayloadOffset() const {
        return getCsrcSize() + (ext ? (4 + getExtSize()) : 0);
    }

    uint8_t *getPayloadData() { return &payload + getPayloadOffset(); }

    size_t getPaddingSize(size_t rtp_size) const {
        if (!padding) return 0;
        auto end = (uint8_t *)this + rtp_size - 1;
        return *end;
    }

    ssize_t getPayloadSize(size_t rtp_size) const {
        auto invalid_size = getPayloadOffset() + getPaddingSize(rtp_size);
        return (ssize_t)rtp_size - invalid_size - 12;
    }

    std::string dumpString(size_t rtp_size) const {
        std::stringstream printer;
        printer << "version:" << (int)version << "\r\n";
        printer << "padding:" << getPaddingSize(rtp_size) << "\r\n";
        printer << "ext:" << getExtSize() << "\r\n";
        printer << "csrc:" << getCsrcSize() << "\r\n";
        printer << "mark:" << (int)mark << "\r\n";
        printer << "pt:" << (int)pt << "\r\n";
        printer << "seq:" << ntohs(seq) << "\r\n";
        printer << "stamp:" << ntohl(stamp) << "\r\n";
        printer << "ssrc:" << ntohl(ssrc) << "\r\n";
        printer << "rtp size:" << rtp_size << "\r\n";
        printer << "payload offset:" << getPayloadOffset() << "\r\n";
        printer << "payload size:" << getPayloadSize(rtp_size) << "\r\n";
        return printer.str();
    }

} PACKED;

#if defined(_WIN32)
#pragma pack(pop)
#endif

#endif // FPV_WFB_RTP_H
