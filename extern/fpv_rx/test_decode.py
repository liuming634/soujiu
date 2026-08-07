import sys, time, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fpv_rx

r = fpv_rx.Receiver()
ok = r.start('0bda:8812', 161, 0, 'gs.key', 7669206)
print(f'start={ok}', flush=True)

time.sleep(2)

for i in range(30):
    fd = r.recv(100)
    if fd.valid:
        data = bytes(fd.data)
        print(f'Frame {i}: codec={fd.codec} size={len(data)} is_keyframe={fd.is_keyframe}', flush=True)
        if data[:4] == b'\x00\x00\x00\x01':
            nal_type = (data[4] >> 1) & 0x3F
            print(f'  NAL type={nal_type}', flush=True)
        else:
            print(f'  First bytes: {data[:4].hex()}', flush=True)
    else:
        print(f'Frame {i}: no data', flush=True)
    time.sleep(0.2)

r.stop()
print('DONE', flush=True)
