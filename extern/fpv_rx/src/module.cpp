#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "receiver.h"

namespace py = pybind11;

PYBIND11_MODULE(fpv_rx, m) {
    m.doc() = "FPV WFB-ng RTL8812AU receiver";

    py::class_<FrameData>(m, "FrameData")
        .def_readonly("codec", &FrameData::codec)
        .def_property_readonly("data", [](const FrameData &self) {
            return py::bytes(
                reinterpret_cast<const char*>(self.data.data()),
                self.data.size());
        })
        .def_readonly("width", &FrameData::width)
        .def_readonly("height", &FrameData::height)
        .def_readonly("is_keyframe", &FrameData::is_keyframe)
        .def_readonly("valid", &FrameData::valid)
        .def("__bool__", [](const FrameData &self) { return self.valid; });

    py::class_<FpvReceiver>(m, "Receiver")
        .def(py::init<>())
        .def("start", &FpvReceiver::start,
             py::arg("vid_pid"), py::arg("channel"),
             py::arg("channel_width") = 0,
             py::arg("key_path") = "gs.key",
             py::arg("link_id") = 7669206,
             py::arg("codec") = "h265",
             py::arg("video_width") = 1280,
             py::arg("video_height") = 720,
             py::arg("fps") = 120)
        .def("recv", &FpvReceiver::recv,
             py::arg("timeout_ms") = 5000)
        .def("stop", &FpvReceiver::stop)
        .def_property_readonly("connected", &FpvReceiver::connected);
}
