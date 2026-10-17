# 超级马里奥随机地图版

> Python + Pygame 实现的 NES SMB1 风格平台跳跃游戏，地图随机生成，支持触控和上帝模式。

![Python](https://img.shields.io/badge/python-3.13+-blue.svg)
![Pygame](https://img.shields.io/badge/pygame-2.6+-green.svg)
![Platform](https://img.shields.io/badge/platform-windows-lightgrey.svg)

## ✨ 特性

- 🎲 **随机地图生成** — 每次启动关卡地形、砖块、敌人、管道全部随机
- 🕹️ **完整 SMB1 核心机制** — 跳跃、下蹲、撞砖、顶砖块、管道进地下、关卡通关
- 🔥 **三种形态** — 小马里奥 / 大马里奥 / 火焰马里奥（火球抛物线 + 反弹）
- ⭐ **隐藏问号砖块** — 前8列安全区外随机生成，被顶后显形
- 🕳️ **地下世界** — 管道进入后硬切场景，纯黑背景 + 灰蓝砖块 + 怪物换色
- 👻 **多种敌人** — Goomba 踩扁 / Koopa 变壳踢飞 / 壳撞墙反弹
- 🏆 **关卡系统** — 时间换积分、剩余生命、金币累计、最高分持久化
- 📱 **Beta 触控模式** — 虚拟摇杆 + 半透明按钮，移动端友好
- 🎮 **上帝模式** — 无限生命 + 隐藏砖块可见 + 14 个调试快捷键
- 🎨 **原版 NES 资源** — MarioWiki 16×16 原生像素素材

## 🚀 快速开始

```bash
# 安装依赖
pnpm install pygame pillow  # 或: pip install pygame pillow

# 正常启动
python mario.py

# 上帝模式（无限命 + 调试）
python mario.py god

# 触控模式（移动端）
python mario.py touch

# 双开
python mario.py god touch
```

## 🎮 操作

### 键盘

| 按键 | 功能 |
|------|------|
| A / ← | 向左移动 |
| D / → | 向右移动 |
| W / ↑ / Space | 跳跃 |
| S / ↓ | 下蹲 / 进入管道 |
| Z / X / J / Shift | 射击（火焰马里奥） |
| Ctrl | 加速跑 |
| P | 暂停 |
| N | 返回上一关（复活） |
| R | 重启游戏 |
| Enter | 标题页开始 / RESHUFFLE MAP |

### 触控

| 区域 | 功能 |
|------|------|
| 左半屏按下拖动 | 虚拟摇杆（方向） |
| 右半屏任何位置 | 跳跃 |
| [FIRE] 小圆 | 射击（仅火焰形态） |
| [DOWN] 小圆 | 下蹲 / 管道进入 |

> 桌面测试：**鼠标左键**模拟触摸

## 📦 项目结构

```
mario/
├── mario.py              # 主游戏（单文件，~4000+ 行）
├── DEBUG.md              # 上帝模式 + 触控模式 完整调试指南
├── assets/
│   ├── MainCharacters/
│   │   ├── Mario/        # 小/大/火焰/下蹲/morph sprite + 触控版本
│   │   ├── Goomba/       # 走/踩扁/地下 palette
│   │   ├── KoopaTroopa/  # 绿/蓝地下 palette + 缩壳
│   │   └── Fireball/     # 4帧火球动画
│   ├── Terrain/          # 砖块/问号/管道/地下资源/城堡/隐藏砖块
│   ├── Music/            # BGM（白天/地下/加速/无敌星）+ 音效
│   ├── Fonts/emulogic.ttf  # NES 风格字体
│   └── icon.ico          # 任务栏图标
└── README.md
```

## 🧪 调试（上帝模式）

```bash
python mario.py god        # 启动上帝模式
python mario.py god touch  # 双开
```

### 快捷键速查

```
~     瞬移关卡末尾          F2    清屏敌人
U     永久无敌开关          F3    碰撞盒描边
1/2/3 小/大/火焰马里奥      F4    Debug 状态信息
F9    火焰+15秒无敌星       F5    回出生点
F6    跳到下一关            F10   冻结/解冻敌人
F11   +50 coins            F12   +3 lives
```

详细指南见 [DEBUG.md](DEBUG.md)

## 🎨 资源来源

所有素材均来自 MarioWiki：
- [Mario 系列 sprite](https://www.mariowiki.com/Gallery:Super_Mario_Bros._sprites)
- [地形资源](https://www.mariowiki.com/Gallery:Super_Mario_Bros._tilesets)
- [音频资源](https://www.mariowiki.com/Gallery:Super_Mario_Bros._audio)

## 📜 License

仅供学习参考，游戏素材版权归 Nintendo 所有。
