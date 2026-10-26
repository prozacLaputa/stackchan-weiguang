# Weiguang Home Sans

主屏状态卡专用字形，派生自 **Noto Sans Mono CJK SC**。当前两行布局只使用 Bold 30px 状态标题，运行时固定 `setTextSize(1)`。底部辅助行与顶部「番茄钟」按钮统一使用原生 `efontCN_16`，不使用此字库，也不再缩放旧 24px 点阵。Regular 24px 是此前任务标题使用的字库资源，当前不再调用，链接器会从固件中移除这部分未引用数据。

字体数据遵循 [SIL Open Font License 1.1](OFL-Noto.txt)，原版权与署名见 [NOTICE-Noto.txt](NOTICE-Noto.txt)。派生名称为 Weiguang Home Sans；字体的 OFL 许可独立于项目代码许可。

上游：[notofonts/noto-cjk](https://github.com/notofonts/noto-cjk)，固定修订 `f8d157532fbfaeda587e826d4cd5b21a49186f7c`。下载地址和 SHA-256 见 [sources.json](sources.json)，生成参数和产物校验见 [generated.json](generated.json)。原始 OTF 留在忽略目录，不随固件源码重复保存。

## 重新生成

将 `sources.json` 中的三个文件下载至 `.vendor/noto-home-font/`，安装 Pillow 12.1.1 后，从项目根目录运行：

```sh
python3 checks/generate_home_fonts.py --source .vendor/noto-home-font
```

生成器先验证输入文件 SHA-256，再生成两个 M5GFX `BDFfont` 数据表。像素是原生字号的单色点阵，字形含独立基线和行高，中文及英文字母下伸部不会被原来的 24px 行框裁掉。任务标题覆盖 ASCII、Latin-1、常用标点、CJK 基本区及扩展 A、全角字符；状态只包含公开固件源码中的字符及 ASCII。没有从私人任务名、运行记录或聊天内容抽取字库。

每张索引表含末尾 `U+FFFF` 哨兵，确保 M5GFX 的索引查找遇到缺字时仍在数组内；其余未收录文字沿用 M5GFX 缺字占位，不支持彩色 Emoji。生成器对较宽的 Latin-1 符号仍遵循现有半宽单元限制，个别非 ASCII 符号边缘可能裁切。
