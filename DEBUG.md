# 调试指南

## 启动参数

```bash
python mario.py                          # 正常模式
python mario.py touch                    # Beta 触控模式（手机/鼠标模拟）
python mario.py god                      # 上帝模式（无限命 + 调试快捷键）
python mario.py god touch                # 上帝模式 + 触控（可叠加）
python mario.py debug                    # god 别名
python mario.py touch god                # 参数顺序无关
```

---

## 基础操作（所有模式）

| 按键 | 功能 |
|------|------|
| A / ← | 向左移动 |
| D / → | 向右移动 |
| W / ↑ / Space | 跳跃 |
| S / ↓ | 下蹲（大马里奥）/ 进入管道 |
| Z / X / J / Shift | 射击（火焰马里奥） |
| Ctrl | 加速跑 |
| P | 暂停 |
| N | 返回上一关（复活） |
| R | 重启游戏 |
| Enter | 标题页开始游戏 |

---

## 上帝模式（God Mode）专属

**启动条件**: 命令行带 `god` / `debug` / `-g` 参数

### 内置功能（不需按键）

| 功能 | 说明 |
|------|------|
| **无限生命** | 死亡不扣命，动画结束自动复活，永不 GAME OVER |
| **隐藏砖块可见** | hidden 状态显示半透明方块 + 白色边框（黄色=金币内容，金色=1-Up） |
| **管道进地下正常工作** | BGM 切换、砖块色调、怪物地下 palette |

### 调试快捷键

#### 关卡传送

| 按键 | 功能 | 说明 |
|------|------|------|
| **~** (Backquote) | 瞬移到关卡末尾 | 直接触发通关结算 |
| **F5** | 传送回出生点 | 重置当前关卡（保留 lives） |
| **F6** | 跳到下一关 | 模拟通关，继承 is_big 形态 |

#### 形态切换

| 按键 | 功能 |
|------|------|
| **1** | 强制小马里奥 |
| **2** | 强制大马里奥 |
| **3** | 强制火焰马里奥 |
| **F9** | 火焰马里奥 + 15秒无敌星（彩虹滤镜） |

#### 无敌

| 按键 | 功能 | 说明 |
|------|------|------|
| **U** | 永久无敌开关 | 碰怪不死、火焰不降级、掉坑不死，再次按 U 恢复正常 |

#### 敌人

| 按键 | 功能 | 说明 |
|------|------|------|
| **F2** | 清屏所有敌人 | 彻底删除 goombas + koopas 列表 |
| **F10** | 冻结/解冻敌人 | 敌人原地不动（走路敌人生效，缩壳滑动不冻） |

#### 资源

| 按键 | 功能 |
|------|------|
| **F11** | +50 coins, +5000 score |
| **F12** | +3 lives |

#### 调试显示

| 按键 | 功能 | 说明 |
|------|------|------|
| **F3** | 碰撞盒描边开关 | Mario(绿) / 砖块(蓝) / 管道(绿) / 敌人(红/绿) / 隐藏砖块(黄/金) |
| **F4** | 状态信息开关 | 左上角实时显示 pos/vx/vy/on_ground/is_big/fire_mode/invincible/world/... |

### 所有 God Mode 按键汇总

```
~     瞬移末尾          F2    清屏敌人
U     永久无敌          F3    碰撞盒
1     小马里奥          F4    Debug 信息
2     大马里奥          F5    出生点
3     火焰马里奥        F6    下一关
F9    火焰+无敌星       F10   冻结敌人
F11   +50 coins         F12   +3 lives
```

所有快捷键使用**边沿触发**，防长按连跳。控制台每按一次都有 `[GOD] xxx` 输出。

---

## 触控模式（Touch Mode）专属

**启动条件**: 命令行带 `touch` / `-t` 参数

### 操作布局

```
┌──────────────────┬───────────────────────┐
│                  │                       │
│   左半屏 → 摇杆   │   右半屏 → 跳跃       │
│                  │   (任何位置!)         │
│   (浮动出现)      │                       │
│                  │     [JUMP] 大圆 (r=44)│
│                  │                       │
│                  │  [DOWN] [FIRE] 小圆    │
└──────────────────┴───────────────────────┘
```

| 区域/按钮 | 功能 |
|-----------|------|
| 左半屏按下拖动 | 虚拟摇杆，方向移动 |
| 右半屏任何位置按下 | 跳跃 |
| JUMP 大圆 | 跳跃（视觉提示 + 双保险） |
| FIRE 小圆 | 射击（仅火焰形态显示）+ 加速 |
| DOWN 小圆 | 下蹲 / 管道进入 |

### 跳跃机制

- **边沿触发**: 按下瞬间跳一次，按住不闪跳
- **落地自动复位**: 松开再按 → 连跳
- **滑射**: 左半屏按住摇杆方向，右半屏按按钮 = 边移边打

### 桌面测试

没有触摸屏时，**鼠标左键**模拟触摸：
- 按住左半屏拖动 = 摇杆
- 按住右半屏 = 跳跃
- 移到 FIRE/DOWN 按钮上 = 对应功能

### 主页面触控

- 直接点击"1 PLAYER GAME" / "RESHUFFLE THE MAP" 文字区域选中

---

## 常见问题

### Q: 启动时 `mixer not initialized` 怎么办？
A: 禁用了声卡的环境会自动降级——游戏正常运行，只是没声音。不需要修。

### Q: 跳跃按钮点了不跳？
A: 确保在游戏中（非标题页），马里奥站在地上。右半屏任何位置按下都应该跳。God Mode 下按 F5 回出生点再试。

### Q: FIRE 按钮不出现？
A: FIRE 仅在 **火焰马里奥** 形态显示。God Mode 下按 **3** 切到火焰形态。

### Q: Debug 信息 `expected str, bytes or os.PathLike object, not int`？
A: 已修过，emulogic.ttf 优先加载，fallback 到 Arial。如果还出问题按 F4 关掉。

### Q: 碰撞盒描边看不到？
A: F3 切换开关。只有 camera 可见范围内的物体才描边。

---

## 架构备忘

### 参数检测（模块加载时）
```python
TOUCH_MODE = '--touch' in sys.argv
GOD_MODE   = '--god' in sys.argv
```
→ 两个独立开关，可以叠加（`python mario.py god touch`）

### 无音频降级
`pygame.mixer.init()` 失败时：
- 替换 `pygame.mixer.music` → `_NoopMusic`（所有方法 no-op）
- 替换 `pygame.mixer.Sound` → `_NoopSound`（加载/播放不炸）
- 替换 `pygame.mixer.find_channel` → 返回 `_NoopChannel`
- 游戏照常跑，没声音而已

### 触控输入链路
```
FINGERDOWN/MOUSEBUTTONDOWN → _handle_touch_events(event)
                              ↓ 更新 touch_input dict
                              ↓ 更新 joystick / touch_buttons
主循环每帧:
  mario_move() → 读 touch_input['move_x'] 代替 pygame.key.get_pressed()
  触控跳跃检测 → 边沿触发（_prev_touch_jump）
  _draw_touch_overlay() → 画摇杆 + 按钮覆盖层
```

### 调试快捷键链路
```
主循环每帧:
  pygame.key.get_pressed() → _cur
  _prev_debug_keys（上一帧状态）
  _pressed(k) = _cur[k] and not _prev.get(k, False)  # 边沿触发
  执行对应功能
  更新 _prev_debug_keys
```
