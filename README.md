# kids-youtube-channel

## Clipper — تقطيع الفيديوهات الطويلة لـ Shorts

أداة بتقطّع أي فيديو طويل لكليبات قصيرة بمقاس Shorts (1080×1920).
محتاج بس Python 3 و [ffmpeg](https://ffmpeg.org/download.html).

### تقطيع تلقائي (كليبات متساوية)

```bash
python3 clipper/clip.py auto video.mp4 --length 58
```

بيقطّع الفيديو كله لكليبات 58 ثانية، ولو آخر حتة أقصر من 15 ثانية بيشيلها (`--min-length`).

### تقطيع يدوي (أنت تحدد الأماكن)

اكتب ملف زي `clipper/clips.example.txt` — كل سطر: `البداية النهاية العنوان`:

```bash
python3 clipper/clip.py manual video.mp4 --timestamps clips.txt
```

### الخيارات

| الخيار | المعنى |
|---|---|
| `-o clips/` | فولدر الحفظ |
| `--format blur` | (افتراضي) الصورة كاملة في النص وخلفية مموّهة |
| `--format crop` | يملا الشاشة ويقصّ الجناب |
| `--format original` | يسيب المقاس الأصلي |
