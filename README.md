# kids-youtube-channel

## Clipper — أداة الكليبينج

بتاخد فيديو طويل (ملف عندك أو لينك يوتيوب / تويتش / كيك) وتطلّع منه كليبات قصيرة
بمقاس Shorts و TikTok و Reels (1080×1920)، وممكن تكتب عليها كابشن كلمة بكلمة.

> استخدمها بس مع محتوى من حقك تقطّعه: حملات كليبينج، فيديوهاتك، أو فيديوهات Creative Commons.

### التسطيب (مرة واحدة)

1. نزّل [Python 3](https://www.python.org/downloads/) و [ffmpeg](https://ffmpeg.org/download.html).
2. نزّل المكتبات:
   ```bash
   pip install -r clipper/requirements.txt
   ```

على ويندوز اكتب `python` بدل `python3` في كل الأوامر.

### تقطيع يدوي (أنت بتحدد أحسن اللحظات)

اكتب ملف زي `clipper/clips.example.txt`، كل سطر فيه: `البداية النهاية العنوان`:

```bash
python3 clipper/clip.py manual "https://www.youtube.com/watch?v=..." --timestamps clips.txt --captions
```

### تقطيع تلقائي (كليبات متساوية)

```bash
python3 clipper/clip.py auto video.mp4 --length 58
```

بيقطّع الفيديو كله لكليبات 58 ثانية، ولو آخر حتة أقصر من 15 ثانية بيشيلها (`--min-length`).

### الكابشن

`--captions` بيسمع الفيديو ويكتب الكلام على الشاشة، والكلمة اللي بتتقال بتنوّر أصفر.
أول مرة بس بينزّل موديل Whisper (حوالي نص جيجا).

- `--lang en` لو عارف لغة الفيديو: أسرع وأدق.
- `--whisper-model base` لو جهازك بطيء.

### الخيارات

| الخيار | المعنى |
|---|---|
| `-o clips/` | فولدر الكليبات (الفيديوهات اللي من لينكات بتتحفظ في `downloads/`) |
| `--format blur` | (افتراضي) الصورة كاملة في النص وخلفية مموّهة |
| `--format crop` | يملا الشاشة ويقصّ الجناب |
| `--format original` | يسيب المقاس الأصلي |
| `--captions` | كابشن كلمة بكلمة |
| `--lang` | لغة الكلام، زي `en` أو `fr` أو `ar` (الافتراضي: يكتشفها لوحده) |
| `--whisper-model` | `tiny` / `base` / `small` (افتراضي) / `medium` / `large-v3` |
