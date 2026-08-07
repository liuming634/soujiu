import sys, os, time, cv2, av
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpv_rx

r = fpv_rx.Receiver()
r.start('0bda:8812', 161, 0, 'gs.key', 7669206)
time.sleep(5)

found = False
for i in range(100):
    fd = r.recv(200)
    if fd.valid:
        print(f'FRAME: codec={fd.codec} data_type={type(fd.data)} len={len(fd.data)} is_keyframe={fd.is_keyframe}', flush=True)
        raw = bytes(fd.data)
        print(f'raw: type={type(raw)} len={len(raw)} first_bytes={raw[:8].hex()}', flush=True)
        
        ctx = av.CodecContext.create('hevc', 'r')
        
        # Method 1: parse + decode
        try:
            packets = list(ctx.parse(raw))
            print(f'  parse: {len(packets)} packets', flush=True)
            for p in packets:
                frames = ctx.decode(p)
                for f in frames:
                    arr = f.to_ndarray(format='bgr24')
                    print(f'  DECODED shape={arr.shape}', flush=True)
                    cv2.imwrite('debug_frame.jpg', arr)
                    print('  SAVED!', flush=True)
                    found = True
                    break
                if found: break
        except Exception as e:
            print(f'  parse/decode error: {e}', flush=True)
        
        # Method 2: direct decode
        if not found:
            try:
                for f in ctx.decode(av.Packet(raw)):
                    arr = f.to_ndarray(format='bgr24')
                    print(f'  DIRECT DECODE shape={arr.shape}', flush=True)
                    cv2.imwrite('debug_frame.jpg', arr)
                    found = True
            except Exception as e:
                print(f'  direct decode error: {e}', flush=True)
        
        if found:
            break

if not found:
    print('NO valid frame decoded', flush=True)

r.stop()
print('DONE', flush=True)
