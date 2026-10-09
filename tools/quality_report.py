import os
import sys

import cv2

from app.stages.quality import check_frame

folder = sys.argv[1]
for name in sorted(os.listdir(folder)):
    if name.lower().endswith((".jpg", ".jpeg", ".png")):
        r = check_frame(cv2.imread(os.path.join(folder, name)))
        print(f"{name:30s} blur={r['blur_var']:8.1f} glare={r['glare_frac']:.4f} bright={r['brightness']:6.1f} "
              f"issues={','.join(r['issues']) or 'ok'}")