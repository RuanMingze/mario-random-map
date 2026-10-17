import os
os.environ["SDL_IME_SHOW_UI"] = "0"

import sys
import pygame
import random
import math
import json

# ===== Beta 触控模式：python mario.py touch 启用 =====
TOUCH_MODE = len(sys.argv) > 1 and sys.argv[1].lower() in ('touch', '--touch', '-t')
# ===== 上帝模式：python mario.py god 启用（隐藏砖块可见 + 无限生命） =====
GOD_MODE = any(a.lower() in ('god', '--god', '-g', 'debug') for a in sys.argv[1:])
# 触控跳跃边沿检测前一帧状态（模块级，供 mario_move global 声明）
_prev_touch_jump = False
import win32gui
import win32api
import win32con
import ctypes
import io
from PIL import Image as PILImage

# PyInstaller打包后的资源路径处理
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def asset_path(*parts):
    """获取资源文件的绝对路径"""
    return os.path.join(BASE_DIR, *parts)

def load_gif_frames(filepath):
    """用 PIL 提取 GIF 所有帧，返回 pygame Surface 列表"""
    frames = []
    try:
        pil_img = PILImage.open(filepath)
        while True:
            pil_img.seek(len(frames))
            pil_img.load()
            rgba = pil_img.convert('RGBA')
            surf = pygame.image.fromstring(rgba.tobytes(), rgba.size, 'RGBA').convert_alpha()
            frames.append(surf)
            pil_img.seek(len(frames))
    except EOFError:
        pass
    except Exception:
        pass
    return frames

IMC_GETOPENSTATUS = 0x0005
IMC_SETOPENSTATUS = 0x0006
imm32 = ctypes.WinDLL("imm32", use_last_error=True)

GAME_HWND = None  # 游戏窗口句柄，初始化后设置

def ime_force_english(is_window_focus):
    if not is_window_focus:
        return
    # 使用游戏窗口自身的句柄，而非 GetForegroundWindow()
    # 这样即使焦点变化也能正确获取 IME 句柄
    hwnd = GAME_HWND
    if hwnd is None:
        hwnd = win32gui.GetForegroundWindow()
    if hwnd:
        h_ime = imm32.ImmGetDefaultIMEWnd(hwnd)
        if h_ime:
            win32api.SendMessage(h_ime, win32con.WM_IME_CONTROL, IMC_SETOPENSTATUS, 0)

MARIO_SPRITE_W = 16
MARIO_SPRITE_H = 16
BIG_MARIO_SPRITE_H = 32       # Super Mario (变大后) NES 原图 16×32
CROUCH_SPRITE_H = 22          # SMB1 NES 原版蹲姿 (SMB Super Mario Ducking.png) 16×22
SCALE_TIMES = 3
MARIO_REAL_W = MARIO_SPRITE_W * SCALE_TIMES
MARIO_REAL_H = MARIO_SPRITE_H * SCALE_TIMES
BIG_MARIO_REAL_H = BIG_MARIO_SPRITE_H * SCALE_TIMES    # 96
CROUCH_REAL_H = CROUCH_SPRITE_H * SCALE_TIMES          # 66
BLOCK_RAW = 16
BLOCK_SIZE = BLOCK_RAW * SCALE_TIMES
MARIO_DISPLAY_W = 320
MARIO_DISPLAY_H = 320
HIGH = 540
WIDTH = 960
INITIAL_WORLD_WIDTH = WIDTH * 2
# 世界最大宽度（超过后停止生成与滚动），可根据需要调整
MAX_WORLD_WIDTH = INITIAL_WORLD_WIDTH * 3
SPEEDX = 5
SPRINT_MULTIPLIER = 1.6
RUN_ACCEL = 0.5
RUN_DECEL = 0.5
FPS = 60
FPS_SMOOTHING = 0.1  # 用于平滑FPS显示，减少闪烁
ANIM_SPEED = 6
GRAVITY = 1.2
FRAMES_PER_TIME_TICK = int(0.4 * FPS)
JUMP_POWER = -24
DEATH_JUMP_POWER = -18
# 普通死亡（撞怪）
DEATH_RISE_FRAMES = int(FPS * 0.22)
DEATH_RISE_SPEED = 12
DEATH_PAUSE_FRAMES = int(FPS * 0.5)
# 掉坑死亡
PIT_DEATH_RISE_FRAMES = int(FPS * 0.15)
PIT_DEATH_RISE_SPEED = 8
PIT_DEATH_PAUSE_FRAMES = int(FPS * 0.3)
GOOMBA_VANISH_FRAMES = int(FPS * 0.6)
GOOMBA_SHELL_KILL_BOUNCE_SPEED = 1
GOOMBA_RAW = 16
GOOMBA_SIZE = GOOMBA_RAW * SCALE_TIMES
CHUNK_COLS = WIDTH // BLOCK_SIZE
PIT_CHANCE = 0.04
COIN_SPAWN_CHANCE = 0.12
MIN_PIT_WIDTH = 2
MAX_PIT_WIDTH = 4
MIN_PLATFORM_WIDTH = 2
MAX_PLATFORM_WIDTH = 4
PLATFORM_HEIGHT_OPTIONS = [2, 3, 4]
MAX_PLATFORMS_PER_CHUNK = 4
MIN_QUESTION_BLOCKS_PER_LEVEL = 4
START_SAFE_ZONE_COLS = 8  # 起点保护区列数（前8列不生成平台、坑、怪物）
KOOPA_RAW = 16
KOOPA_WALK_RAW_H = 24
KOOPA_SHELL_RAW_H = 14
KOOPA_SIZE_W = KOOPA_RAW * SCALE_TIMES
KOOPA_WALK_SIZE_H = KOOPA_WALK_RAW_H * SCALE_TIMES
KOOPA_SHELL_SIZE_H = KOOPA_SHELL_RAW_H * SCALE_TIMES
KOOPA_WALK_SPEED = 1.5
KOOPA_SHELL_SPEED = 8
KOOPA_SHELL_RESTORE_FRAMES = int(FPS * 6)
WHITE = (255, 255, 255)
BLUE = (0, 0, 255)
SKY_BLUE = (90, 150, 255)

# 设置 Windows 任务栏图标（必须在窗口创建之前）
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('ruanftrix.mario.game')
except:
    pass

pygame.init()
# 音频初始化：没有声卡时静默降级（游戏照常运行，只是没声音）
try:
    pygame.mixer.init()
    _audio_available = True
except pygame.error:
    _audio_available = False
    # 替换 mixer.music 为空壳代理，所有 .load/.play/.stop/.pause/.unpause 自动 no-op
    class _NoopMusic:
        def load(self, *a, **kw): pass
        def play(self, *a, **kw): pass
        def stop(self, *a, **kw): pass
        def pause(self, *a, **kw): pass
        def unpause(self, *a, **kw): pass
        def set_volume(self, *a, **kw): pass
        def get_pos(self, *a, **kw): return 0
        def get_busy(self, *a, **kw): return False
        def queue(self, *a, **kw): pass
        def fadeout(self, *a, **kw): pass
    pygame.mixer.music = _NoopMusic()
    # 同时替换 Sound 类为空壳，防止 Sound() 加载时炸
    class _NoopSound:
        def __init__(self, *a, **kw): pass
        def play(self, *a, **kw): return None
        def stop(self, *a, **kw): pass
        def set_volume(self, *a, **kw): pass
        def get_length(self, *a, **kw): return 0
        def fadeout(self, *a, **kw): pass
    pygame.mixer.Sound = _NoopSound
    # find_channel 空壳（返回一个空 Channel）
    class _NoopChannel:
        def play(self, *a, **kw): return self
        def stop(self, *a, **kw): pass
        def pause(self, *a, **kw): pass
        def unpause(self, *a, **kw): pass
        def set_volume(self, *a, **kw): pass
        def get_busy(self, *a, **kw): return False
        def queue(self, *a, **kw): pass
    pygame.mixer.find_channel = lambda *a, **kw: _NoopChannel()
pygame.key.stop_text_input()
base_head = "超级马里奥随机地图版 - By Ruanftrix"
pygame.display.set_caption(base_head)
screen = pygame.display.set_mode((WIDTH, HIGH))
clock = pygame.time.Clock()
window_focus = True

# 获取游戏窗口句柄（用于 IME 控制）
try:
    GAME_HWND = pygame.display.get_wm_info()['window']
except Exception:
    GAME_HWND = None

music_dir = asset_path("assets", "Music")
background_music = os.path.join(music_dir, "Daytime-BGM.mp3")
jump_sound_file = os.path.join(music_dir, "Jump.mp3")
death_sound_file = os.path.join(music_dir, "Death.mp3")
goomba_death_sound_file = os.path.join(music_dir, "Goomba-Death.mp3")
death_channel = None
death_wait_for_music = False
obstacles = []
koopas = []

if os.path.exists(background_music):
    pygame.mixer.music.load(background_music)
    pygame.mixer.music.set_volume(0.5)
    # 不立即播放，等进入游戏后再播放
else:
    print(f"Warning: 未找到背景音乐：{background_music}")

jump_sound = None
if os.path.exists(jump_sound_file):
    jump_sound = pygame.mixer.Sound(jump_sound_file)
    jump_sound.set_volume(0.35)
else:
    print(f"Warning: 未找到跳跃音效：{jump_sound_file}")

death_sound = None
if os.path.exists(death_sound_file):
    death_sound = pygame.mixer.Sound(death_sound_file)
    death_sound.set_volume(0.7)
else:
    print(f"Warning: 未找到死亡音效：{death_sound_file}")

goomba_death_sound = None
if os.path.exists(goomba_death_sound_file):
    goomba_death_sound = pygame.mixer.Sound(goomba_death_sound_file)
    goomba_death_sound.set_volume(0.7)
else:
    print(f"Warning: 未找到板栗仔死亡音效：{goomba_death_sound_file}")

gold_sound_file = os.path.join(music_dir, "Gold-coins.mp3")
gold_sound = None
if os.path.exists(gold_sound_file):
    gold_sound = pygame.mixer.Sound(gold_sound_file)
    gold_sound.set_volume(0.25)
else:
    gold_sound = None

pass_sound_file = os.path.join(music_dir, "Pass-the-level.mp3")
pass_sound = None
PASS_SOUND_FRAMES = 0
if os.path.exists(pass_sound_file):
    pass_sound = pygame.mixer.Sound(pass_sound_file)
    pass_sound.set_volume(0.7)
    PASS_SOUND_FRAMES = int(pass_sound.get_length() * FPS)
else:
    print(f"Warning: 未找到通关音效：{pass_sound_file}")

game_over_sound_file = os.path.join(music_dir, "Game-Over.mp3")
game_over_sound = None
if os.path.exists(game_over_sound_file):
    game_over_sound = pygame.mixer.Sound(game_over_sound_file)
    game_over_sound.set_volume(0.7)
else:
    print(f"Warning: 未找到Game Over音效：{game_over_sound_file}")

pause_sound_file = os.path.join(music_dir, "Pause.mp3")
pause_sound = None
if os.path.exists(pause_sound_file):
    pause_sound = pygame.mixer.Sound(pause_sound_file)
    pause_sound.set_volume(0.7)
else:
    print(f"Warning: 未找到暂停音效：{pause_sound_file}")

invincibility_music_file = os.path.join(music_dir, "Invincibility.mp3")
invincibility_music = None
if os.path.exists(invincibility_music_file):
    invincibility_music = pygame.mixer.Sound(invincibility_music_file)
    invincibility_music.set_volume(0.7)
else:
    print(f"Warning: 未找到无敌音效：{invincibility_music_file}")

# 计时器警告音效
timer_warning_sound_file = os.path.join(music_dir, "Timer-Warning.mp3")
timer_warning_sound = None
if os.path.exists(timer_warning_sound_file):
    timer_warning_sound = pygame.mixer.Sound(timer_warning_sound_file)
    timer_warning_sound.set_volume(0.7)
else:
    print(f"Warning: 未找到计时器警告音效：{timer_warning_sound_file}")

# 加速版BGM
fast_bgm_file = os.path.join(music_dir, "Daytime-BGM-Fast.mp3")
fast_bgm_available = os.path.exists(fast_bgm_file)
print(f"加速版BGM: {'已找到' if fast_bgm_available else '未找到'}")

# BGM时长配置（秒）
ORIGINAL_BGM_DURATION = 188  # 原始BGM时长
FAST_BGM_DURATION = 128  # 加速版BGM时长

# 死亡画面用 Mario idle 精灵
death_screen_mario = pygame.image.load(asset_path('assets', 'MainCharacters', 'Mario', 'idle.png')).convert_alpha()
death_screen_mario = pygame.transform.scale(death_screen_mario, (MARIO_REAL_W, MARIO_REAL_H))

def flip_sprites(sprites):
    flipped_list = []
    for sprite in sprites:
        flipped = pygame.transform.flip(sprite, True, False)
        flipped_list.append(flipped)
    return flipped_list

def load_sprite_sheets(dir1, dir2, cut_w, cut_h, scale_w, scale_h, direction=False):
    path = asset_path("assets", dir1, dir2)
    if not os.path.exists(path):
        raise FileNotFoundError(f"精灵文件夹不存在：{path}")
    images = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f)) and f.endswith(".png")]

    all_sprites = {}
    for image in images:
        sprite_sheet = pygame.image.load(os.path.join(path, image)).convert_alpha()
        sprites = []
        frame_count = sprite_sheet.get_width() // cut_w
        for i in range(frame_count):
            surface = pygame.Surface((cut_w, cut_h), pygame.SRCALPHA, 32)
            rect = pygame.Rect(i * cut_w, 0, cut_w, cut_h)
            surface.blit(sprite_sheet, (0, 0), rect)
            final_sprite = pygame.transform.scale(surface, (scale_w, scale_h))
            sprites.append(final_sprite)

        name = image.replace('.png', '')
        if direction:
            all_sprites[f"{name}_right"] = sprites
            all_sprites[f"{name}_left"] = flip_sprites(sprites)
        else:
            all_sprites[name] = sprites
    return all_sprites

block_img = pygame.image.load(asset_path("assets", "Terrain", "Ground.png")).convert_alpha()
block_img = pygame.transform.scale(block_img, (BLOCK_SIZE, BLOCK_SIZE))
# 地下砖块原版资源（SMB1 NES palette）
_underground_ground_path = asset_path("assets", "Terrain", "Ground_Underground.png")
if os.path.exists(_underground_ground_path):
    block_img_underground = pygame.image.load(_underground_ground_path).convert_alpha()
    block_img_underground = pygame.transform.scale(block_img_underground, (BLOCK_SIZE, BLOCK_SIZE))
else:
    block_img_underground = block_img.copy()  # 回退到地表图
# 地下问号砖块（地下 palette，用原版动画 GIF 的 6 帧）
_underground_qblock_gif = asset_path("assets", "Terrain", "Question_Block_Underground.gif")
question_block_frames_underground = []
if os.path.exists(_underground_qblock_gif):
    _raw_frames = load_gif_frames(_underground_qblock_gif)
    question_block_frames_underground = [pygame.transform.scale(f, (BLOCK_SIZE, BLOCK_SIZE)) for f in _raw_frames]
if not question_block_frames_underground:
    # 回退：用静态图复制
    _uqb_png = asset_path("assets", "Terrain", "Question_Block_Underground.png")
    if os.path.exists(_uqb_png):
        _uqb_img = pygame.image.load(_uqb_png).convert_alpha()
        _uqb_img = pygame.transform.scale(_uqb_img, (BLOCK_SIZE, BLOCK_SIZE))
        question_block_frames_underground = [_uqb_img for _ in range(6)]
obstacle_img = pygame.transform.scale(block_img, (BLOCK_SIZE, BLOCK_SIZE))
empty_block_img = None
empty_block_path = asset_path('assets', 'Terrain', 'Empty-Block.png')
if os.path.exists(empty_block_path):
    empty_block_img = pygame.image.load(empty_block_path).convert_alpha()
    empty_block_img = pygame.transform.scale(empty_block_img, (BLOCK_SIZE, BLOCK_SIZE))
else:
    empty_block_img = block_img

# 地下 empty block：opened ? block 在地下用 Ground_Underground 替代（SMB1 NES palette 一致）
empty_block_img_underground = block_img_underground

blocks = []
block_rows = 2
start_y = HIGH - block_rows * BLOCK_SIZE
world_width = INITIAL_WORLD_WIDTH
world_ended = False
obstacles = []
coins_in_world = []
# 被顶起的方块视觉偏移状态：key=id(rect) -> {'rect': rect, 't': int, 'max_t': int}
bumped_blocks = {}

# 会话级关卡缓存（窗口存活期间有效，关闭窗口后清除）
# key: WORLD_STR (如 "", "1-2"), value: 关卡状态字典
session_level_cache = {}
# 记录每个关卡已缓存的最大列数（用于增量更新缓存）
level_cache_max_col = {}

# 云朵（Small-cloud 原图比 Big-cloud 大一倍，需多缩小一级）
big_cloud_raw = pygame.image.load(asset_path("assets", "Terrain", "Big-cloud.png")).convert_alpha()
small_cloud_raw = pygame.image.load(asset_path("assets", "Terrain", "Small-cloud.png")).convert_alpha()
big_cloud_img = pygame.transform.scale(big_cloud_raw, (big_cloud_raw.get_width() // 4, big_cloud_raw.get_height() // 4))
small_cloud_img = pygame.transform.scale(small_cloud_raw, (small_cloud_raw.get_width() // 8, small_cloud_raw.get_height() // 8))

# 生成云朵（随机分布在天空中，不重叠）
clouds = []
def generate_clouds(start_x, end_x):
    for x in range(start_x, end_x, random.randint(400, 700)):
        is_big = random.random() > 0.5
        img = big_cloud_img if is_big else small_cloud_img
        y = random.randint(50, 100)
        new_rect = pygame.Rect(x, y, img.get_width(), img.get_height())
        # 检查与已有云是否重叠
        overlap = any(new_rect.colliderect(c['rect']) for c in clouds)
        if not overlap:
            clouds.append({'rect': new_rect, 'img': img})

generate_clouds(0, INITIAL_WORLD_WIDTH)

fortress_img = pygame.image.load(asset_path("assets", "Terrain", "Fortress.png")).convert_alpha()
fortress_img = pygame.transform.scale(fortress_img, (80 * SCALE_TIMES, 80 * SCALE_TIMES))

# 库巴城堡（原图144×176，按比例缩放但限制最大高度）
bowser_castle_img_raw = pygame.image.load(asset_path("assets", "Terrain", "Castle.png")).convert_alpha()
BOWSER_CASTLE_RAW_W = 144
BOWSER_CASTLE_RAW_H = 176
# 限制最大高度为 start_y（地面y坐标），避免超出屏幕顶部
BOWSER_CASTLE_MAX_H = start_y
BOWSER_CASTLE_SCALE = min(SCALE_TIMES, BOWSER_CASTLE_MAX_H / BOWSER_CASTLE_RAW_H)
BOWSER_CASTLE_W = int(BOWSER_CASTLE_RAW_W * BOWSER_CASTLE_SCALE)
BOWSER_CASTLE_H = int(BOWSER_CASTLE_RAW_H * BOWSER_CASTLE_SCALE)
bowser_castle_img = pygame.transform.scale(bowser_castle_img_raw, (BOWSER_CASTLE_W, BOWSER_CASTLE_H))

# 起点城堡（根据关卡选择）
fortress_rect = pygame.Rect(BLOCK_SIZE, start_y - fortress_img.get_height(), fortress_img.get_width(), fortress_img.get_height())

# 通关城堡
castle_img = pygame.image.load(asset_path("assets", "Terrain", "Fortress.png")).convert_alpha()
castle_img = pygame.transform.scale(castle_img, (80 * SCALE_TIMES, 80 * SCALE_TIMES))

# 水管
pipe_img_raw = pygame.image.load(asset_path("assets", "Terrain", "Warp-Pipe.png")).convert_alpha()
PIPE_WIDTH = int(BLOCK_SIZE * 2)
PIPE_HEIGHT = int(BLOCK_SIZE * 2)
pipe_img = pygame.transform.scale(pipe_img_raw, (PIPE_WIDTH, PIPE_HEIGHT))
pipes = []  # 存储水管的矩形列表
pipe_entry_pipes = []  # 可进入地下的水管列表（存 rect + 标记）
PIPE_SPAWN_CHANCE = 0.05  # 水管生成概率（降低到 5%）
PIPE_UNDERGROUND_CHANCE = 0.50  # 每个水管成为可进入管道的概率（50%，调高便于测试）
UNDERGROUND_BG_COLOR = (0, 0, 0)  # SMB1 NES 地下背景：纯黑（原版卡带取色器确认）

# 地下 BGM
underground_bgm_file = os.path.join(music_dir, "SMB_Underground_BGM.flac")
pipe_enter_sound_file = os.path.join(music_dir, "SMB_Pipe.wav")

# 管道进入动画状态机
pipe_enter_state = 'none'  # 'none' | 'entering' | 'exiting'
pipe_enter_timer = 0
_current_enter_pipe = None  # 当前正在进入的管道 rect
is_underground = False  # True = 地下场景（黑背景 + 地下 BGM + 砖墙渲染）

def _switch_bgm(go_underground):
    """切换地表/地下 BGM"""
    try:
        if go_underground and _underground_bgm_loaded:
            pygame.mixer.music.pause()
            pygame.mixer.music.load(underground_bgm_file)
            pygame.mixer.music.play(-1)
        elif not go_underground and background_music and os.path.exists(background_music):
            pygame.mixer.music.pause()
            pygame.mixer.music.load(background_music)
            pygame.mixer.music.play(-1)
    except Exception:
        pass

# 标题界面Logo
logo_raw = pygame.image.load(asset_path("assets", "Terrain", "In-game_Logo.png")).convert_alpha()
LOGO_SCALE = 2.5
logo_img = pygame.transform.scale(logo_raw, (int(logo_raw.get_width() * LOGO_SCALE), int(logo_raw.get_height() * LOGO_SCALE)))

# 标题界面插画
illustration_raw = pygame.image.load(asset_path("assets", "Terrain", "Illustration.png")).convert_alpha()
ILLUSTRATION_W = WIDTH
ILLUSTRATION_H = int(illustration_raw.get_height() * (ILLUSTRATION_W / illustration_raw.get_width()))
illustration_img = pygame.transform.scale(illustration_raw, (ILLUSTRATION_W, ILLUSTRATION_H))

# 标题界面选择指示器
select_indicator_raw = pygame.image.load(asset_path("assets", "Terrain", "Selectindicator.png")).convert_alpha()

# 无敌星
stars_in_world = []  # 存储世界中的无敌星
star_generated_this_level = False  # 本关卡是否已生成过无敌星
question_blocks = []  # 存储问号砖块
hidden_blocks = []  # 隐藏砖块（SMB1 原版 invisible ? block）—— 实体但不绘制，被顶后显现
emerging_stars = []  # 存储从问号砖块中冒出来的无敌星
mushrooms_in_world = []  # 世界中出现的 Super Mushroom 道具
fire_flowers_in_world = []  # 世界中出现的 Fire Flower 道具
fireballs = []  # Mario 发射的火球
STAR_SPAWN_CHANCE = 0.01  # 平台上生成无敌星的概率（1%，再次调低）
MUSHROOM_SPAWN_CHANCE = 0.3  # 顶问号砖块出蘑菇的概率（30%）
MIN_QUESTION_BLOCKS_PER_LEVEL = 4
HIDDEN_BLOCK_SPAWN_CHANCE = 0.03  # 每列生成隐藏砖块的概率（3%）
MAX_HIDDEN_BLOCKS_PER_LEVEL = 3   # 每关最多隐藏砖块数
INVINCIBILITY_DURATION = 30 * FPS  # 无敌持续时间 30 秒
INVINCIBILITY_GRACE = FPS  # 无敌宽限期 1 秒（滤镜消失但仍无敌）
invincible_timer = 0  # 无敌计时器
invincible_grace_timer = 0  # 无敌宽限期计时器（滤镜消失但仍无敌）
original_bgm = None  # 保存原始BGM用于恢复

# 时间警告相关状态
timer_warning_triggered = False  # 是否已触发时间警告
bgm_switched_to_fast = False  # BGM是否已切换到加速版
saved_bgm_position = 0  # 保存BGM暂停时的播放位置（毫秒）
waiting_for_invincibility = False  # 是否正在等待无敌星结束后再切换
waiting_for_warning_finish = False  # 是否正在等待Timer-Warning播放完成
pending_fast_bgm_position = 0  # 等待警告播放完成后要切换到的加速版BGM位置
timer_warning_channel = None  # 计时器警告音效播放通道

goomba_walk_frames = []
for frame_file in ["Walk1.png", "Walk2.png"]:
    frame = pygame.image.load(asset_path("assets", "MainCharacters", "Goomba", frame_file)).convert_alpha()
    frame = pygame.transform.scale(frame, (GOOMBA_SIZE, GOOMBA_SIZE))
    goomba_walk_frames.append(frame)

goomba_dead_img = pygame.image.load(asset_path("assets", "MainCharacters", "Goomba", "Dead_Goomba.png")).convert_alpha()
goomba_dead2_img = pygame.image.load(asset_path("assets", "MainCharacters", "Goomba", "Dead2.png")).convert_alpha()

goomba_dead_img = pygame.transform.scale(goomba_dead_img, (GOOMBA_SIZE, GOOMBA_SIZE // 2))
goomba_dead2_img = pygame.transform.scale(goomba_dead2_img, (GOOMBA_SIZE, GOOMBA_SIZE))

koopa_walk_frames = []
for frame_file in ["Run1.png", "Run2.png"]:
    frame = pygame.image.load(asset_path("assets", "MainCharacters", "KoopaTroopa", frame_file)).convert_alpha()
    frame = pygame.transform.scale(frame, (KOOPA_SIZE_W, KOOPA_WALK_SIZE_H))
    koopa_walk_frames.append(frame)
koopa_walk_frames_left = flip_sprites(koopa_walk_frames)
koopa_sheet_right = koopa_walk_frames_left
koopa_sheet_left = koopa_walk_frames
koopa_shell_img = pygame.image.load(asset_path("assets", "MainCharacters", "KoopaTroopa", "Greenshell.png")).convert_alpha()
koopa_shell_img = pygame.transform.scale(koopa_shell_img, (KOOPA_SIZE_W, KOOPA_SHELL_SIZE_H))

# ========== 地下 palette 怪物 sprite ==========
# Goomba 地下（灰色，和 castle/night 共用 palette）
goomba_walk_frames_underground = []
_goomba_ug_gif = asset_path("assets", "MainCharacters", "Goomba", "Underground.gif")
if os.path.exists(_goomba_ug_gif):
    _raw = load_gif_frames(_goomba_ug_gif)
    goomba_walk_frames_underground = [pygame.transform.scale(f, (GOOMBA_SIZE, GOOMBA_SIZE)) for f in _raw]
if not goomba_walk_frames_underground:
    goomba_walk_frames_underground = goomba_walk_frames  # 回退

# Koopa 地下（蓝色 troopa palette）
koopa_walk_frames_underground_right = []
_koopa_ug_gif = asset_path("assets", "MainCharacters", "KoopaTroopa", "Blue_Underground.gif")
if os.path.exists(_koopa_ug_gif):
    _raw = load_gif_frames(_koopa_ug_gif)
    koopa_walk_frames_underground_right = [pygame.transform.scale(f, (KOOPA_SIZE_W, KOOPA_WALK_SIZE_H)) for f in _raw]
if not koopa_walk_frames_underground_right:
    koopa_walk_frames_underground_right = koopa_walk_frames_left  # 回退（原来 right 是 flipped 的）
koopa_walk_frames_underground_left = flip_sprites(koopa_walk_frames_underground_right)
koopa_sheet_right_underground = koopa_walk_frames_underground_left
koopa_sheet_left_underground = koopa_walk_frames_underground_right
# Koopa shell 地下 palette：用 Buzzy Shell Underground 替代
koopa_shell_img_underground = koopa_shell_img
_ksh_path = asset_path("assets", "MainCharacters", "KoopaTroopa", "Shell_Underground.png")
if os.path.exists(_ksh_path):
    _ksh = pygame.image.load(_ksh_path).convert_alpha()
    koopa_shell_img_underground = pygame.transform.scale(_ksh, (KOOPA_SIZE_W, KOOPA_SHELL_SIZE_H))

# Goomba dead 地下 palette（灰色）
goomba_dead_img_underground = goomba_dead_img
goomba_dead2_img_underground = goomba_dead2_img
_gd_ug_path = asset_path("assets", "MainCharacters", "Goomba", "Dead_Underground.png")
if os.path.exists(_gd_ug_path):
    _gd_ug = pygame.image.load(_gd_ug_path).convert_alpha()
    goomba_dead_img_underground = pygame.transform.scale(_gd_ug, (GOOMBA_SIZE, GOOMBA_SIZE // 2))
goomba_dead_img = pygame.transform.scale(goomba_dead_img, (GOOMBA_SIZE, GOOMBA_SIZE // 2))

death_mario_img = pygame.image.load(asset_path("assets", "MainCharacters", "Mario", "death.png")).convert_alpha()
death_mario_img = pygame.transform.scale(death_mario_img, (MARIO_REAL_W, MARIO_REAL_H))

# Super Mario (变大后, SMB1 NES 原版) 精灵
_big_dir = asset_path("assets", "MainCharacters", "Mario")

def _scale_big(name, h_raw):
    return pygame.transform.scale(
        pygame.image.load(os.path.join(_big_dir, name)).convert_alpha(),
        (MARIO_REAL_W, h_raw * SCALE_TIMES)
    )

BIG_IDLE_RIGHT = _scale_big("big_idle.png", 32)
BIG_IDLE_LEFT = pygame.transform.flip(BIG_IDLE_RIGHT, True, False)

BIG_JUMP_RIGHT = _scale_big("big_jump.png", 32)
BIG_JUMP_LEFT = pygame.transform.flip(BIG_JUMP_RIGHT, True, False)

BIG_CROUCH_RIGHT = _scale_big("big_crouch.png", 22)   # SMB1 NES 原版蹲姿 16×22
BIG_CROUCH_LEFT = pygame.transform.flip(BIG_CROUCH_RIGHT, True, False)

# 走路动画 3 帧（SMB1 NES Walking GIF 拆出）
BIG_RUN_FRAMES_RIGHT = []
for _ri in range(3):
    try:
        BIG_RUN_FRAMES_RIGHT.append(_scale_big(f"big_run_{_ri}.png", 32))
    except FileNotFoundError:
        pass
BIG_RUN_FRAMES_LEFT = [pygame.transform.flip(f, True, False) for f in BIG_RUN_FRAMES_RIGHT]

# Morph 变形动画 (SMB1 NES 原版小↔大, 10帧 16x32)
MORPH_FRAMES = []
for _mi in range(10):
    try:
        MORPH_FRAMES.append(_scale_big(f"morph_{_mi}.png", 32))
    except FileNotFoundError:
        pass
MORPH_FRAMES_LEFT = [pygame.transform.flip(f, True, False) for f in MORPH_FRAMES]

# Super Mushroom 道具 (SMB1 原版 16x16)
super_mushroom_img = None
_mush_path = asset_path("assets", "Terrain", "SuperMushroom.png")
if os.path.exists(_mush_path):
    super_mushroom_img = pygame.transform.scale(
        pygame.image.load(_mush_path).convert_alpha(), (MARIO_REAL_W, MARIO_REAL_W))

# Fire Flower 道具 (SMB1 原版 GIF 4帧动画)
fire_flower_img = None
_fireflower_path = asset_path("assets", "Terrain", "Fire_Flower.gif")
if os.path.exists(_fireflower_path):
    _ff_frames = load_gif_frames(_fireflower_path)
    if _ff_frames:
        # 取第一帧当静态图（简化：不做动画）
        fire_flower_img = pygame.transform.scale(_ff_frames[0], (MARIO_REAL_W, MARIO_REAL_W))
if fire_flower_img is None:
    # 回退：用 mushroom 图片替代
    fire_flower_img = super_mushroom_img

# ========== Fire Mario 原版 sprite（全部来自 MarioWiki SMB1 资源） ==========
def _load_fire_sprite(filename, target_h):
    """加载 Fire Mario sprite 并缩放到目标高度（保持宽高比）"""
    path = asset_path("assets", "MainCharacters", "Mario", filename)
    if os.path.exists(path):
        img = pygame.image.load(path).convert_alpha()
        scale = target_h / img.get_height()
        return pygame.transform.scale(img, (int(img.get_width() * scale), target_h))
    return None

# Fire Mario idle：用 fire_walk.gif 第一帧（和 walk 同 palette）
_fire_walk_gif_path = asset_path("assets", "MainCharacters", "Mario", "fire_walk.gif")
_fire_idle_right = None
if os.path.exists(_fire_walk_gif_path):
    _raw_frames = load_gif_frames(_fire_walk_gif_path)
    if _raw_frames:
        _fire_idle_right = pygame.transform.scale(_raw_frames[0], (MARIO_REAL_W, BIG_MARIO_REAL_H))
if _fire_idle_right is None:
    _fire_idle_path = asset_path("assets", "MainCharacters", "Mario", "fire_idle.png")
    if os.path.exists(_fire_idle_path):
        _fire_idle_right = pygame.transform.scale(
            pygame.image.load(_fire_idle_path).convert_alpha(), (MARIO_REAL_W, BIG_MARIO_REAL_H))
if _fire_idle_right is None:
    _fire_idle_right = BIG_IDLE_RIGHT
_fire_idle_left = pygame.transform.flip(_fire_idle_right, True, False)

# Fire Mario jump（SMB Fire Mario Jumping.png）
_fire_jump_right = _load_fire_sprite("fire_jump.png", BIG_MARIO_REAL_H)
if _fire_jump_right is None: _fire_jump_right = BIG_JUMP_RIGHT
_fire_jump_left = pygame.transform.flip(_fire_jump_right, True, False)

# Fire Mario crouch（SMB Fire Mario Ducking.png，高较小）
_fire_crouch_right = _load_fire_sprite("fire_crouch.png", CROUCH_REAL_H)
if _fire_crouch_right is None: _fire_crouch_right = BIG_CROUCH_RIGHT
_fire_crouch_left = pygame.transform.flip(_fire_crouch_right, True, False)

# Fire Mario walk 3 帧（SMB Fire Mario Walking.gif）
_fire_walk_gif = asset_path("assets", "MainCharacters", "Mario", "fire_walk.gif")
_fire_run_frames_right = []
if os.path.exists(_fire_walk_gif):
    _raw = load_gif_frames(_fire_walk_gif)
    _fire_run_frames_right = [pygame.transform.scale(f, (MARIO_REAL_W, BIG_MARIO_REAL_H)) for f in _raw]
if not _fire_run_frames_right:
    _fire_run_frames_right = BIG_RUN_FRAMES_RIGHT.copy()
_fire_run_frames_left = [pygame.transform.flip(f, True, False) for f in _fire_run_frames_right]

# ========== 火球（SMB Fireball.gif，4帧动画） ==========
fireball_frames = []
_fireball_gif = asset_path("assets", "Terrain", "Fireball.gif")
if os.path.exists(_fireball_gif):
    _raw = load_gif_frames(_fireball_gif)
    fireball_frames = [pygame.transform.scale(f, (24, 24)) for f in _raw]
if not fireball_frames:
    # 回退：简单圆形
    _fb = pygame.Surface((24, 24), pygame.SRCALPHA)
    pygame.draw.circle(_fb, (255, 140, 0, 255), (12, 12), 10)
    pygame.draw.circle(_fb, (255, 220, 50, 255), (12, 12), 6)
    fireball_frames = [_fb]
fireball_img = fireball_frames[0]  # 保留单帧引用用于简单绘制

# 顶部状态栏资源
STATUS_FONT_PATH = asset_path('assets', 'Fonts', 'emulogic.ttf')
STATUS_FONT_SIZE = 16 * SCALE_TIMES // 3
STATUS_BAR_TOP_PADDING = 6
try:
    status_font = pygame.font.Font(STATUS_FONT_PATH, STATUS_FONT_SIZE)
except Exception:
    status_font = pygame.font.SysFont(None, STATUS_FONT_SIZE)

# 选择指示器缩放（现在STATUS_FONT_SIZE已定义）
SELECT_INDICATOR_SCALE = STATUS_FONT_SIZE / 21  # 按字体高度缩放（原图21px高）
SELECT_INDICATOR_W = int(select_indicator_raw.get_width() * SELECT_INDICATOR_SCALE)
SELECT_INDICATOR_H = int(select_indicator_raw.get_height() * SELECT_INDICATOR_SCALE)
select_indicator_img = pygame.transform.scale(select_indicator_raw, (SELECT_INDICATOR_W, SELECT_INDICATOR_H))

coin_icon = None
coin_frames_world = []
coin_frames_icon = []
COIN_WORLD_SIZE = max(6, int(BLOCK_SIZE * 0.8))
COIN_ICON_SIZE = 8 * SCALE_TIMES

# 无敌星动画
star_frames = []
for i in range(1, 5):
    star_path = asset_path('assets', 'Terrain', f'Star{i}.png')
    if os.path.exists(star_path):
        star_img = pygame.image.load(star_path).convert_alpha()
        star_img = pygame.transform.scale(star_img, (COIN_WORLD_SIZE, COIN_WORLD_SIZE))
        star_frames.append(star_img)
# 问号砖块动画（优先使用 Questionmark-block 资源）
question_block_frames = []
castle_frames = []
for i in range(1, 7):
    p = asset_path('assets', 'Terrain', f'Questionmark-block{i}.png')
    if os.path.exists(p):
        try:
            img = pygame.image.load(p).convert_alpha()
            question_block_frames.append(pygame.transform.scale(img, (BLOCK_SIZE, BLOCK_SIZE)))
        except Exception:
            pass

for i in range(1, 6):
    p = asset_path('assets', 'Terrain', f'CoinCastle{i}.png')
    if os.path.exists(p):
        try:
            img = pygame.image.load(p).convert_alpha()
            coin_frames_world.append(pygame.transform.scale(img, (COIN_WORLD_SIZE, COIN_WORLD_SIZE)))
            coin_frames_icon.append(pygame.transform.scale(img, (COIN_ICON_SIZE, COIN_ICON_SIZE)))
            if not question_block_frames:
                question_block_frames.append(pygame.transform.scale(img, (BLOCK_SIZE, BLOCK_SIZE)))
        except Exception:
            pass

# 回退到单张 Gold-coins.png 或空列表
if not coin_frames_world:
    coin_img_path = asset_path('assets', 'Terrain', 'Gold-coins.png')
    if os.path.exists(coin_img_path):
        raw_coin = pygame.image.load(coin_img_path).convert_alpha()
        rw, rh = raw_coin.get_width(), raw_coin.get_height()
        if rw >= rh and rw % rh == 0:
            frame_count = rw // rh
            for i in range(frame_count):
                surf = pygame.Surface((rh, rh), pygame.SRCALPHA)
                surf.blit(raw_coin, (0, 0), pygame.Rect(i * rh, 0, rh, rh))
                coin_frames_world.append(pygame.transform.scale(surf, (COIN_WORLD_SIZE, COIN_WORLD_SIZE)))
                coin_frames_icon.append(pygame.transform.scale(surf, (COIN_ICON_SIZE, COIN_ICON_SIZE)))
        else:
            coin_frames_world.append(pygame.transform.scale(raw_coin, (COIN_WORLD_SIZE, COIN_WORLD_SIZE)))
            coin_frames_icon.append(pygame.transform.scale(raw_coin, (COIN_ICON_SIZE, COIN_ICON_SIZE)))

# 问号砖块开口音效
question_block_open_sound = None
open_sound_file = asset_path('assets', 'Music', 'Open.mp3')
if os.path.exists(open_sound_file):
    question_block_open_sound = pygame.mixer.Sound(open_sound_file)
    question_block_open_sound.set_volume(0.6)

# 顶块音效
hit_block_sound = None
hit_block_sound_file = asset_path('assets', 'Music', 'Hit-Block.mp3')
if os.path.exists(hit_block_sound_file):
    hit_block_sound = pygame.mixer.Sound(hit_block_sound_file)
    hit_block_sound.set_volume(0.6)
else:
    hit_block_sound = None

# Super Mushroom 吃到 / 变大 / 变小音效 (SMB1 NES 原版 .oga)
power_up_sound = None
_power_up_file = asset_path('assets', 'Music', 'SMB_Power_Up.oga')
if os.path.exists(_power_up_file):
    try:
        power_up_sound = pygame.mixer.Sound(_power_up_file)
        power_up_sound.set_volume(0.35)
    except Exception:
        power_up_sound = None

power_down_sound = None
_power_down_file = asset_path('assets', 'Music', 'SMB_Power_Down.oga')
if os.path.exists(_power_down_file):
    try:
        power_down_sound = pygame.mixer.Sound(_power_down_file)
        power_down_sound.set_volume(0.8)
    except Exception:
        power_down_sound = None

# 砖块破碎音效 (SMB1 NES 原版 Break Block.oga)
break_block_sound = None
_break_file = asset_path('assets', 'Music', 'SMB_Break_Block.wav')
if os.path.exists(_break_file):
    try:
        break_block_sound = pygame.mixer.Sound(_break_file)
        break_block_sound.set_volume(0.8)
    except Exception:
        break_block_sound = None

# 管道进入音效（SMB1 原版）
pipe_enter_sound = None
if os.path.exists(pipe_enter_sound_file):
    try:
        pipe_enter_sound = pygame.mixer.Sound(pipe_enter_sound_file)
        pipe_enter_sound.set_volume(0.6)
    except Exception:
        pipe_enter_sound = None

# 地下 BGM 预加载（pygame.mixer.music 需要文件路径）
_underground_bgm_loaded = os.path.exists(underground_bgm_file)

# 砖块 sprite 切片（用于破碎粒子）
_brick_sprite_path = asset_path('assets', 'Terrain', 'Brick_Block_SMB.png')
BRICK_BLOCK_IMG = pygame.image.load(_brick_sprite_path).convert_alpha() if os.path.exists(_brick_sprite_path) else None
# SMB1 原版砖块被顶碎 → 切成 4 块（左上、右上、左下、右下），各 8×8 原尺寸
# 碎片会被 scale 到 BLOCK_SIZE/2 × BLOCK_SIZE/2
def _make_brick_pieces(rect):
    """从砖块 rect 创建 4 块带真实贴图的碎片"""
    pieces = []
    if BRICK_BLOCK_IMG:
        src_w, src_h = BRICK_BLOCK_IMG.get_size()  # 16x16
        half = src_w // 2  # 8
        scale = BLOCK_SIZE // src_w  # 3
        # 4 个源切片 + 目标尺寸
        src_rects = [
            (0, 0, half, half),       # 左上
            (half, 0, half, half),    # 右上
            (0, half, half, half),    # 左下
            (half, half, half, half), # 右下
        ]
        dst_sizes = [(half*scale, half*scale)] * 4  # 24x24 每块
        for i, (sx, sy, sw, sh) in enumerate(src_rects):
            surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
            surf.blit(BRICK_BLOCK_IMG, (0, 0), (sx, sy, sw, sh))
            surf = pygame.transform.scale(surf, dst_sizes[i])
            pieces.append(surf)
    return pieces

# ---------- 砖块破碎粒子 ----------
# SMB1 原版：顶碎砖块 → 4 块飞溅碎片（左上、右上、左下、右下）
class BrickPiece:
    __slots__ = ['x', 'y', 'w', 'h', 'vx', 'vy', 'gravity', 'life', 'max_life', 'surf', 'rotating', '_angle']
    def __init__(self, x, y, surf, vx, vy, rotating=False):
        self.x = float(x)
        self.y = float(y)
        self.surf = surf.copy()
        self.w = surf.get_width()
        self.h = surf.get_height()
        self.vx = float(vx)
        self.vy = float(vy)
        self.gravity = 0.6
        self.max_life = 55
        self.life = self.max_life
        self.rotating = rotating
        self._angle = 0

    def update(self):
        self.vy += self.gravity
        self.x += self.vx
        self.y += self.vy
        self.life -= 1
        if self.rotating:
            self._angle += 6   # 旋转动画增强动感

    def draw(self, screen, camera_x):
        if self.life <= 0:
            return
        alpha = self.life / self.max_life
        if self.rotating and self._angle % 360 != 0:
            s = pygame.transform.rotate(self.surf, self._angle)
        else:
            s = self.surf
        if alpha < 1.0:
            fade = s.copy()
            fade.set_alpha(int(255 * alpha))
            s = fade
        draw_x = int(self.x - camera_x)
        draw_y = int(self.y)
        screen.blit(s, (draw_x, draw_y))

# 游戏状态
coins = 0
lives = 3
WORLD_STR = '1-1'
TIME_START = 300

def get_level_time_start(world_str):
    return 400 if world_str.endswith('-4') else TIME_START

time_left = get_level_time_start(WORLD_STR)
time_frame_counter = 0
score = 0

# 标题界面状态
game_state = 'title'  # 'title', 'intro', 'playing', 'game_over'
title_menu_index = 0  # 0=1 PLAYER GAME, 1=RESHUFFLE THE MAP
title_blink_timer = 0
reshuffle_hint_timer = 0  # RESHUFFLE 成功提示倒计时（帧）
reshuffle_hint_text = ''

# ======== 触控模式全局状态 ========
if TOUCH_MODE:
    # 触控输入字典（mario_move 读取这个代替 pygame.key.get_pressed()）
    touch_input = {
        'move_x': 0,      # -1, 0, 1 左/停/右
        'jump': False,    # 跳跃按钮
        'action': False,  # 射击/加速
        'crouch': False,  # 下蹲/管道
    }
    # 虚拟摇杆状态（浮动式：左半区按下时出现）
    joystick = {
        'active': False,
        'base_x': 0,     # 摇杆中心
        'base_y': 0,
        'stick_x': 0,    # 摇杆头位置
        'stick_y': 0,
        'finger': None,  # 跟踪的手指ID
        'radius': 60,    # 摇杆可拖动半径
    }
    # 触控按钮状态（JUMP 独立大圆 + FIRE/DOWN 小圆 + 右半屏区域跳跃）
    touch_buttons = {
        'jump':   {'x': WIDTH - 80,  'y': HIGH - 110, 'r': 44, 'held': False, 'finger': None},
        'action': {'x': WIDTH - 180, 'y': HIGH - 95,  'r': 32, 'held': False, 'finger': None},
        'crouch': {'x': WIDTH - 260, 'y': HIGH - 75,  'r': 28, 'held': False, 'finger': None},
    }
    # 鼠标模拟触控（桌面测试用）
    _mouse_as_touch = {'active': False, 'finger': 0}

def _handle_touch_events(event):
    """处理 pygame.FINGER*/MOUSE* 事件，更新 touch_input / joystick / touch_buttons"""
    global touch_input, joystick, touch_buttons, _mouse_as_touch

    # ---------- 鼠标模拟（桌面） ----------
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        mx, my = event.pos
        # 左半区 → 摇杆
        if mx < WIDTH // 2:
            _mouse_as_touch['active'] = True
            joystick['active'] = True
            joystick['base_x'] = mx
            joystick['base_y'] = my
            joystick['stick_x'] = mx
            joystick['stick_y'] = my
            joystick['finger'] = 'mouse'
            touch_input['move_x'] = 0
        else:
            # 右半区 → 跳跃（任何位置！）+ FIRE/DOWN 精准按钮
            touch_input['jump'] = True
            # FIRE/DOWN 精确按钮
            for name, btn in touch_buttons.items():
                dx, dy = mx - btn['x'], my - btn['y']
                if dx*dx + dy*dy <= btn['r'] * btn['r']:
                    btn['held'] = True
                    btn['finger'] = 'mouse'
                    if name == 'action': touch_input['action'] = True
                    elif name == 'crouch': touch_input['crouch'] = True
                    break
            # 按钮外右半屏：只跳跃（已经设置 jump=True）

    elif event.type == pygame.MOUSEMOTION and _mouse_as_touch['active']:
        mx, my = event.pos
        if joystick['active'] and joystick['finger'] == 'mouse':
            dx = mx - joystick['base_x']
            dy = my - joystick['base_y']
            dist = math.hypot(dx, dy)
            r = joystick['radius']
            if dist > r:
                joystick['stick_x'] = joystick['base_x'] + dx / dist * r
                joystick['stick_y'] = joystick['base_y'] + dy / dist * r
            else:
                joystick['stick_x'] = mx
                joystick['stick_y'] = my
            nx = dx / r if r > 0 else 0
            if abs(nx) < 0.2: nx = 0
            touch_input['move_x'] = 1 if nx > 0 else (-1 if nx < 0 else 0)
        # 右半屏 → 跳跃 + FIRE/DOWN/JUMP 按钮检测
        if mx >= WIDTH // 2:
            touch_input['jump'] = True
            for name, btn in touch_buttons.items():
                dx, dy = mx - btn['x'], my - btn['y']
                _in_btn = dx*dx + dy*dy <= btn['r'] * btn['r']
                if _in_btn and not btn['held']:
                    btn['held'] = True
                    btn['finger'] = 'mouse'
                    if name == 'action': touch_input['action'] = True
                    elif name == 'crouch': touch_input['crouch'] = True
                elif not _in_btn and btn['finger'] == 'mouse':
                    btn['held'] = False
                    btn['finger'] = None
                    if name == 'action': touch_input['action'] = False
                    elif name == 'crouch': touch_input['crouch'] = False
        else:
            # 移到左半屏 → 停止跳跃
            touch_input['jump'] = False

    elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
        if _mouse_as_touch['active']:
            _mouse_as_touch['active'] = False
        # 右半屏抬起 → 停止跳跃
        touch_input['jump'] = False
        if joystick['active'] and joystick['finger'] == 'mouse':
            joystick['active'] = False
            joystick['finger'] = None
            touch_input['move_x'] = 0
        for name, btn in touch_buttons.items():
            if btn['finger'] == 'mouse':
                btn['held'] = False
                btn['finger'] = None
                if name == 'jump': touch_input['jump'] = False
                elif name == 'action': touch_input['action'] = False
                elif name == 'crouch': touch_input['crouch'] = False

    # ---------- 多点触控（移动端） ----------
    elif event.type == pygame.FINGERDOWN:
        fx = event.x * WIDTH
        fy = event.y * HIGH
        fid = event.finger_id
        if fx < WIDTH // 2:
            # 左半区 → 摇杆（优先占用）
            if not joystick['active']:
                joystick['active'] = True
                joystick['base_x'] = fx
                joystick['base_y'] = fy
                joystick['stick_x'] = fx
                joystick['stick_y'] = fy
                joystick['finger'] = fid
                touch_input['move_x'] = 0
        else:
            # 右半区 → 跳跃 + FIRE/DOWN 按钮（按钮区按住=双触发）
            touch_input['jump'] = True
            for name, btn in touch_buttons.items():
                dx, dy = fx - btn['x'], fy - btn['y']
                if dx*dx + dy*dy <= btn['r'] * btn['r'] and btn['finger'] is None:
                    btn['held'] = True
                    btn['finger'] = fid
                    if name == 'action': touch_input['action'] = True
                    elif name == 'crouch': touch_input['crouch'] = True
                    break

    elif event.type == pygame.FINGERMOTION:
        fid = event.finger_id
        fx = event.x * WIDTH
        fy = event.y * HIGH
        if joystick['active'] and joystick['finger'] == fid:
            dx = fx - joystick['base_x']
            dy = fy - joystick['base_y']
            dist = math.hypot(dx, dy)
            r = joystick['radius']
            if dist > r:
                joystick['stick_x'] = joystick['base_x'] + dx / dist * r
                joystick['stick_y'] = joystick['base_y'] + dy / dist * r
            else:
                joystick['stick_x'] = fx
                joystick['stick_y'] = fy
            nx = dx / r if r > 0 else 0
            if abs(nx) < 0.2: nx = 0
            touch_input['move_x'] = 1 if nx > 0 else (-1 if nx < 0 else 0)
        # 移动端：手指移到右半屏 → 跳跃 + FIRE/DOWN 按钮检测
        if fx >= WIDTH // 2:
            touch_input['jump'] = True
            for name, btn in touch_buttons.items():
                dx, dy = fx - btn['x'], fy - btn['y']
                _in_btn = dx*dx + dy*dy <= btn['r'] * btn['r']
                if _in_btn and btn['finger'] is None:
                    btn['held'] = True
                    btn['finger'] = fid
                    if name == 'action': touch_input['action'] = True
                    elif name == 'crouch': touch_input['crouch'] = True
                elif not _in_btn and btn['finger'] == fid:
                    btn['held'] = False
                    btn['finger'] = None
                    if name == 'action': touch_input['action'] = False
                    elif name == 'crouch': touch_input['crouch'] = False

    elif event.type == pygame.FINGERUP:
        fid = event.finger_id
        # 右半屏任意手指抬起 → 停止跳跃
        touch_input['jump'] = False
        if joystick['active'] and joystick['finger'] == fid:
            joystick['active'] = False
            joystick['finger'] = None
            touch_input['move_x'] = 0
        for name, btn in touch_buttons.items():
            if btn['finger'] == fid:
                btn['held'] = False
                btn['finger'] = None
                if name == 'action': touch_input['action'] = False
                elif name == 'crouch': touch_input['crouch'] = False

def _draw_touch_overlay(screen, camera_x=0, mario=None):
    """绘制虚拟摇杆 + 触控按钮（半透明覆盖层）
    FIRE 按钮仅在 Fire Mario 形态时显示，变小/死亡后自动隐藏"""
    if not TOUCH_MODE: return
    _is_fire = bool(mario and mario.fire_mode and not mario.dead)
    overlay = pygame.Surface((WIDTH, HIGH), pygame.SRCALPHA)
    if joystick['active']:
        bx, by = int(joystick['base_x']), int(joystick['base_y'])
        sx, sy = int(joystick['stick_x']), int(joystick['stick_y'])
        r = joystick['radius']
        pygame.draw.circle(overlay, (255, 255, 255, 50), (bx, by), r)
        pygame.draw.circle(overlay, (255, 255, 255, 100), (bx, by), r, 2)
        pygame.draw.circle(overlay, (255, 255, 255, 150), (sx, sy), r // 2)
        pygame.draw.circle(overlay, (200, 200, 200, 200), (sx, sy), r // 2, 2)
    # 按钮：FIRE 仅 Fire Mario 时画；DOWN 始终画
    btn_labels = {'jump': 'JUMP', 'action': 'FIRE', 'crouch': 'DOWN'}
    for name, btn in touch_buttons.items():
        if name == 'action' and not _is_fire:
            # 非 Fire Mario：停止 held 状态
            if btn['held']:
                btn['held'] = False
                btn['finger'] = None
                touch_input['action'] = False
            continue
        color = (255, 200, 50, 180) if btn['held'] else (255, 255, 255, 90)
        outline = (255, 255, 255, 220) if btn['held'] else (255, 255, 255, 120)
        pygame.draw.circle(overlay, color, (btn['x'], btn['y']), btn['r'])
        pygame.draw.circle(overlay, outline, (btn['x'], btn['y']), btn['r'], 2)
    screen.blit(overlay, (0, 0))
    try:
        _lbl_font = pygame.font.SysFont(None, 20, bold=True)
        for name, btn in touch_buttons.items():
            if name == 'action' and not _is_fire:
                continue
            lbl = btn_labels.get(name, '')
            surf = _lbl_font.render(lbl, True, (255, 255, 255))
            rect = surf.get_rect(center=(btn['x'], btn['y']))
            screen.blit(surf, rect)
    except Exception:
        pass
APP_DATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'MarioGame')
os.makedirs(APP_DATA_DIR, exist_ok=True)
HIGH_SCORE_FILE = os.path.join(APP_DATA_DIR, 'highscore.json')

def load_high_score():
    """从本地JSON加载最高分"""
    try:
        if os.path.exists(HIGH_SCORE_FILE):
            with open(HIGH_SCORE_FILE, 'r') as f:
                data = json.load(f)
                return data.get('high_score', 0)
    except Exception:
        pass
    return 0

def save_high_score(s):
    """保存最高分到本地JSON"""
    try:
        with open(HIGH_SCORE_FILE, 'w') as f:
            json.dump({'high_score': s}, f)
    except Exception:
        pass

high_score = load_high_score()

# 通关状态
castle_rect = pygame.Rect(0, 0, 0, 0)
castle_spawned = False
pass_timer = 0
pass_channel = None
pass_phase = 0  # 0=未触发, 1=走向城堡, 2=隐藏等待音效
pass_mario_hidden = False
time_convert_step = 0  # 动态计算的每帧时间转换步长
time_to_convert = 0  # 剩余待转换的时间

# 死亡画面状态
death_screen_timer = 0
death_screen_phase = 0  # 0=正常, 1=显示死亡画面, 2=GAME OVER
game_over_channel = None
pass_settlement = False  # 通关结算标记
is_final_world = False  # 是否为最终关（8-4）
prev_world_str = ''  # 死亡前的关卡（用于 START+A 恢复）
level_intro = True  # 关卡开始时的介绍画面

def is_bowser_stage(world_str):
    """判断当前关卡是否为x-3或x-4（使用库巴城堡）"""
    parts = world_str.split('-')
    if len(parts) != 2:
        return False
    stage = int(parts[1])
    return stage in (3, 4)

def get_fortress_img():
    """获取起点城堡图片（只有x-4使用库巴城堡）"""
    parts = WORLD_STR.split('-')
    stage = int(parts[1]) if len(parts) == 2 else 0
    return bowser_castle_img if stage == 4 else fortress_img

def get_castle_img():
    """获取终点城堡图片（只有x-3使用库巴城堡）"""
    parts = WORLD_STR.split('-')
    stage = int(parts[1]) if len(parts) == 2 else 0
    return bowser_castle_img if stage == 3 else castle_img


def save_level_to_cache():
    """将当前关卡的完整地形状态保存到会话缓存"""
    global WORLD_STR, session_level_cache, level_cache_max_col
    global blocks, obstacles, coins_in_world, pipes, clouds
    global world_width, world_ended, castle_rect, castle_spawned
    global fortress_rect, stars_in_world, star_generated_this_level
    global question_blocks, hidden_blocks, emerging_stars, goombas, koopas

    # 将 pygame.Rect 序列化为元组方便存储
    def rect_to_tuple(r):
        return (r.x, r.y, r.width, r.height)
    
    cache_entry = {
        'blocks': [rect_to_tuple(r) for r in blocks],
        'obstacles': [rect_to_tuple(r) for r in obstacles],
        'coins': [{'rect': rect_to_tuple(c['rect']), 'frame': c['frame']} for c in coins_in_world],
        'pipes': [rect_to_tuple(p) for p in pipes],
        'clouds': [
            {'x': c['rect'].x, 'y': c['rect'].y, 'is_big': c['img'] == big_cloud_img}
            for c in clouds
        ],
        'world_width': world_width,
        'world_ended': world_ended,
        'castle_spawned': castle_spawned,
        'castle_rect': rect_to_tuple(castle_rect) if castle_spawned else None,
        'fortress_rect': rect_to_tuple(fortress_rect),
        'stars_generated': star_generated_this_level,
        # 仅缓存问号砖块的位置（不保存运行时的已打开/动画状态），重开时会还原为未被顶的初始状态
        'question_blocks': [
            {'rect': rect_to_tuple(q['rect']), 'state': 'idle', 'anim_frame': 0, 'anim_timer': 0}
            for q in question_blocks
        ],
        # 隐藏砖块：缓存其位置和初始状态（hidden），重开时重置为未发现
        'hidden_blocks': [
            {'rect': rect_to_tuple(hb['rect']), 'state': 'hidden', 'content': hb.get('content', 'coin'), 'anim_timer': 0}
            for hb in hidden_blocks
        ],
        # 不在缓存中保存运行时冒出的无敌星（重开时不应保留）
        # 存储敌人初始位置，重开时始终恢复为存活/行走状态
        'enemy_positions': [
            {'type': 'goomba', 'x': g.rect.x, 'y': g.rect.y, 'dead': False}
            for g in goombas
        ] + [
            {'type': 'koopa', 'x': k.rect.x, 'y': k.rect.y, 'state': 'walk', 'direction': k.direction}
            for k in koopas
        ],
    }
    session_level_cache[WORLD_STR] = cache_entry
    level_cache_max_col[WORLD_STR] = world_width // BLOCK_SIZE


def restore_level_from_cache(level_key):
    """从会话缓存恢复指定关卡的地形状态，返回 (goombas_list, koopas_list) 或 False"""
    global blocks, obstacles, coins_in_world, pipes, clouds
    global world_width, world_ended, castle_rect, castle_spawned
    global fortress_rect, stars_in_world, star_generated_this_level
    global question_blocks, hidden_blocks, emerging_stars, WORLD_STR, goombas, koopas

    if level_key not in session_level_cache:
        return False
    
    entry = session_level_cache[level_key]
    WORLD_STR = level_key
    
    def tuple_to_rect(t):
        return pygame.Rect(t[0], t[1], t[2], t[3])
    
    # 恢复地形
    blocks = [tuple_to_rect(t) for t in entry['blocks']]
    obstacles = [tuple_to_rect(t) for t in entry['obstacles']]
    coins_in_world = [
        {'rect': tuple_to_rect(c['rect']), 'frame': c['frame'], 'timer': 0}
        for c in entry['coins']
    ]
    pipes = [tuple_to_rect(p) for p in entry['pipes']]
    clouds = []
    for c_data in entry['clouds']:
        img = big_cloud_img if c_data['is_big'] else small_cloud_img
        clouds.append({'rect': pygame.Rect(c_data['x'], c_data['y'], img.get_width(), img.get_height()), 'img': img})
    
    world_width = entry['world_width']
    world_ended = entry['world_ended']
    castle_spawned = entry['castle_spawned']
    if castle_spawned and entry['castle_rect']:
        castle_rect = tuple_to_rect(entry['castle_rect'])
    else:
        castle_rect = pygame.Rect(0, 0, 0, 0)
    fortress_rect = tuple_to_rect(entry['fortress_rect'])
    star_generated_this_level = entry['stars_generated']
    stars_in_world = []  # 重置无敌星（每次重关不保留拾取状态）
    question_blocks = [
        {'rect': tuple_to_rect(q['rect']), 'state': q.get('state', 'idle'), 'anim_frame': q.get('anim_frame', 0), 'anim_timer': q.get('anim_timer', 0)}
        for q in entry.get('question_blocks', [])
    ]
    # 恢复隐藏砖块（状态：hidden 或 revealed）
    hidden_blocks = [
        {'rect': tuple_to_rect(hb['rect']), 'state': hb.get('state', 'hidden'), 'content': hb.get('content', 'coin'), 'anim_timer': hb.get('anim_timer', 0)}
        for hb in entry.get('hidden_blocks', [])
    ]
    # 不恢复运行时的冒出星星（重开时不应保留）
    emerging_stars = []
    
    # 恢复敌人位置
    restored_goombas = []
    restored_koopas = []
    for e in entry.get('enemy_positions', []):
        if e['type'] == 'goomba':
            g = Goomba(e['x'], e['y'])
            if e['dead']:
                g.die()
            restored_goombas.append(g)
        elif e['type'] == 'koopa':
            k = KoopaTroopa(e['x'], e['y'], direction=e.get('direction', -1))
            k.state = e.get('state', 'walk')
            restored_koopas.append(k)
    
    return restored_goombas, restored_koopas

def extend_world_to(target_width):
    global world_width
    global world_ended
    global castle_rect
    global castle_spawned
    if target_width <= world_width:
        return
    # 不超过最大宽度
    if target_width > MAX_WORLD_WIDTH:
        target_width = MAX_WORLD_WIDTH
        world_ended = True
    start_col = world_width // BLOCK_SIZE
    end_col = target_width // BLOCK_SIZE
    if end_col > start_col:
        generate_world_segment(start_col, end_col)
    # 分段刷怪（在新生成的列内生成敌人）
    try:
        spawn_enemies_in_segment(start_col, end_col)
    except NameError:
        pass
    world_width = target_width
    # 延伸云朵
    generate_clouds(start_col * BLOCK_SIZE, target_width)
    # 世界到达最大宽度时生成通关城堡
    if world_ended and not castle_spawned:
        end_castle = get_castle_img()
        castle_x = world_width - end_castle.get_width() - BLOCK_SIZE
        castle_y = start_y - end_castle.get_height()
        castle_rect = pygame.Rect(castle_x, castle_y, end_castle.get_width(), end_castle.get_height())
        castle_spawned = True
    # 保存扩展后的关卡布局到会话缓存
    save_level_to_cache()

def generate_world_segment(start_col, end_col):
    global star_generated_this_level
    hole_columns = set()
    # 计算终点安全区域（城堡前5格不允许坑和平台）
    end_castle_img = get_castle_img()
    castle_col = (world_width - end_castle_img.get_width() - BLOCK_SIZE) // BLOCK_SIZE if castle_spawned else (MAX_WORLD_WIDTH - end_castle_img.get_width() - BLOCK_SIZE) // BLOCK_SIZE
    safe_zone_start = castle_col - 5  # 城堡前5格

    # 起点保护区（前START_SAFE_ZONE_COLS列不生成坑和平台）
    start_safe_zone_end = START_SAFE_ZONE_COLS

    # 如果是生成首段（start_col == 0），保留至少一屏的安全地面
    safe_margin = CHUNK_COLS
    col = start_col + max(3, safe_margin) if start_col == 0 else max(start_col + 3, start_safe_zone_end)

    while col < end_col - 3:
        # 在安全区域内不生成坑（包括起点保护区和终点保护区）
        if col >= safe_zone_start or col < start_safe_zone_end:
            col += 1
            continue

        if random.random() < PIT_CHANCE:
            pit_width = random.randint(MIN_PIT_WIDTH, MAX_PIT_WIDTH)
            for pit_col in range(col, min(end_col - 2, col + pit_width)):
                if pit_col < safe_zone_start and pit_col >= start_safe_zone_end:
                    hole_columns.add(pit_col)
            col += pit_width + 2
        else:
            col += 1

    # 生成地面方块（3行基础地面）
    for col in range(start_col, end_col):
        if col in hole_columns:
            continue
        for row in range(block_rows):
            bx = col * BLOCK_SIZE
            by = start_y + row * BLOCK_SIZE
            blocks.append(pygame.Rect(bx, by, BLOCK_SIZE, BLOCK_SIZE))

    # ========= 生成水管 =========
    pipe_col = max(start_col + 5, start_safe_zone_end)
    last_pipe_col = None
    while pipe_col < min(end_col - 3, safe_zone_start - 2):
        if last_pipe_col is not None:
            min_next = last_pipe_col + PIPE_WIDTH // BLOCK_SIZE + 9
            if pipe_col < min_next:
                pipe_col = min_next
                continue
        if random.random() < PIPE_SPAWN_CHANCE:
            # 检查该位置是否有地面且不在坑上
            if pipe_col not in hole_columns:
                pipe_x = pipe_col * BLOCK_SIZE
                # 管道高度：2 格（短管道，Mario 可以跳上）
                pipe_height = BLOCK_SIZE * 2
                pipe_y = start_y - pipe_height
                pipe_rect = pygame.Rect(pipe_x, pipe_y, PIPE_WIDTH, pipe_height)
                # 检查是否与已有障碍物或方块重叠
                if not any(pipe_rect.colliderect(obs) for obs in obstacles) and \
                   not any(pipe_rect.colliderect(blk) for blk in blocks):
                    pipes.append(pipe_rect)
                    obstacles.append(pipe_rect)
                    # 50% 概率成为可进入地下的管道
                    if random.random() < PIPE_UNDERGROUND_CHANCE:
                        pipe_entry_pipes.append(pipe_rect)
                        print(f"[DEBUG] 可进入管道生成: x={pipe_x}, top={pipe_y}, bottom={pipe_y + pipe_height}")
                    last_pipe_col = pipe_col
            pipe_col += 1
        else:
            pipe_col += 1

    # 生成平台（在安全区域外，包括起点保护区和终点保护区）
    platform_count = random.randint(2, MAX_PLATFORMS_PER_CHUNK)
    for _ in range(platform_count):
        platform_width = random.randint(MIN_PLATFORM_WIDTH, MAX_PLATFORM_WIDTH)
        platform_height = random.choice(PLATFORM_HEIGHT_OPTIONS)
        # 确保平台不在安全区域内（起点保护区和终点保护区）
        max_start = min(end_col - platform_width - 2, safe_zone_start - platform_width)
        min_start = max(start_col + 2, start_safe_zone_end)
        if max_start <= min_start:
            continue
        platform_start = random.randint(min_start, max_start)

        # 平台块列表
        platform_blocks = []
        can_place_platform = True
        for offset in range(platform_width):
            px = (platform_start + offset) * BLOCK_SIZE
            py = start_y - platform_height * BLOCK_SIZE
            rect = pygame.Rect(px, py, BLOCK_SIZE, BLOCK_SIZE)
            if any(rect.colliderect(obs) for obs in blocks + obstacles + platform_blocks):
                can_place_platform = False
                break
            platform_blocks.append(rect)

        if not can_place_platform:
            continue

        for rect in platform_blocks:
            obstacles.append(rect)

        # 平台上有概率生成成群的金币（大小与方块相同），并在方块上方保留下边距
        try:
            if coin_frames_world and random.random() < COIN_SPAWN_CHANCE:
                group_w = random.randint(1, platform_width)
                start_offset = random.randint(0, max(0, platform_width - group_w))
                # 增加安全边距，确保金币不会太靠近砖块
                bottom_margin = BLOCK_SIZE // 2
                # 在平台的不同列位尝试放置金币，避免与方块/障碍重叠或位于屏幕上方
                coin_w = coin_frames_world[0].get_width()
                coin_h = coin_frames_world[0].get_height()
                min_y = STATUS_FONT_SIZE + 4
                placed = False
                # 尝试在平台上多个位置寻找不重叠的空位
                for offset_try in range(platform_width):
                    idx = start_offset + offset_try
                    if idx < 0 or idx >= len(platform_blocks):
                        continue
                    blk = platform_blocks[idx]
                    cx = blk.x + (BLOCK_SIZE - coin_w) // 2
                    cy = blk.y - coin_h - bottom_margin
                    rect = pygame.Rect(cx, cy, coin_w, coin_h)
                    # 跳过高度太高的情况（避免在状态栏/天上）
                    if rect.top < min_y:
                        continue
                    # 检查是否与已有方块或障碍重叠（使用膨胀的碰撞箱确保不重叠）
                    expanded_rect = rect.inflate(4, 4)  # 膨胀4像素确保有间隙
                    if any(r.colliderect(expanded_rect) for r in blocks + obstacles):
                        continue
                    # 通过后放置
                    coins_in_world.append({'rect': rect, 'frame': random.randint(0, max(0, len(coin_frames_world)-1)), 'timer': 0})
                    placed = True
                    break
                # 如果没有找到合适位置，则不放置该组金币
        except NameError:
            pass

        # 平台上有小概率生成无敌星（1-3关卡不在此生成）
        if star_frames and WORLD_STR != '1-3' and random.random() < STAR_SPAWN_CHANCE and not stars_in_world and not star_generated_this_level:
            # 只在平台上生成问号砖块，并替换掉原来的平台块
            mid_offset = platform_width // 2
            if mid_offset < len(platform_blocks):
                blk = platform_blocks[mid_offset]
                q_rect = pygame.Rect(blk.x, blk.y, BLOCK_SIZE, BLOCK_SIZE)
                q_rect_above = q_rect.move(0, -BLOCK_SIZE)
                q_rect_below = q_rect.move(0, BLOCK_SIZE)
                if any(q_rect_above.colliderect(r) for r in blocks + obstacles):
                    continue
                if any(q_rect_below.colliderect(r) for r in blocks + obstacles):
                    continue
                if not any(q['rect'].colliderect(q_rect) for q in question_blocks):
                    if not any(q_rect.colliderect(pipe_rect) for pipe_rect in pipes):
                        if blk in obstacles:
                            obstacles.remove(blk)
                        question_blocks.append({'rect': q_rect, 'state': 'idle', 'anim_frame': 0, 'anim_timer': 0})
                        obstacles.append(q_rect)
                        star_generated_this_level = True

    # 1-3关卡生成一个无敌星（在所有平台生成完成后）
    if WORLD_STR == '1-3' and star_frames and not stars_in_world and not star_generated_this_level:
        # 收集所有已生成的平台
        all_platforms = []
        current_platform = []
        for obs in obstacles:
            if obs.y < start_y:  # 平台在地面之上
                if not current_platform or abs(obs.x - current_platform[-1].x) == BLOCK_SIZE:
                    current_platform.append(obs)
                else:
                    if current_platform:
                        all_platforms.append(current_platform)
                    current_platform = [obs]
        if current_platform:
            all_platforms.append(current_platform)
        
        # 随机选择一个平台放置无敌星
        if all_platforms:
            chosen_platform = random.choice(all_platforms)
            mid_offset = len(chosen_platform) // 2
            if mid_offset < len(chosen_platform):
                blk = chosen_platform[mid_offset]
                q_rect = pygame.Rect(blk.x, blk.y, BLOCK_SIZE, BLOCK_SIZE)
                q_rect_above = q_rect.move(0, -BLOCK_SIZE)
                q_rect_below = q_rect.move(0, BLOCK_SIZE)
                if not any(q_rect_above.colliderect(r) for r in blocks + obstacles) and not any(q_rect_below.colliderect(r) for r in blocks + obstacles):
                    if not any(q['rect'].colliderect(q_rect) for q in question_blocks):
                        if not any(q_rect.colliderect(pipe_rect) for pipe_rect in pipes):
                            if blk in obstacles:
                                obstacles.remove(blk)
                            question_blocks.append({'rect': q_rect, 'state': 'idle', 'anim_frame': 0, 'anim_timer': 0})
                            obstacles.append(q_rect)
                            star_generated_this_level = True

    # 确保每关至少有最少数量的问号砖块
    if len(question_blocks) < MIN_QUESTION_BLOCKS_PER_LEVEL:
        candidate_platform_blocks = [obs for obs in obstacles if obs.y < start_y and obs not in pipes]
        random.shuffle(candidate_platform_blocks)
        for blk in candidate_platform_blocks:
            if len(question_blocks) >= MIN_QUESTION_BLOCKS_PER_LEVEL:
                break
            q_rect = pygame.Rect(blk.x, blk.y, BLOCK_SIZE, BLOCK_SIZE)
            q_rect_above = q_rect.move(0, -BLOCK_SIZE)
            q_rect_below = q_rect.move(0, BLOCK_SIZE)
            if any(q_rect_above.colliderect(r) for r in blocks + obstacles):
                continue
            if any(q_rect_below.colliderect(r) for r in blocks + obstacles):
                continue
            if any(q['rect'].colliderect(q_rect) for q in question_blocks):
                continue
            if any(q_rect.colliderect(pipe_rect) for pipe_rect in pipes):
                continue
            if blk in obstacles:
                obstacles.remove(blk)
            question_blocks.append({'rect': q_rect, 'state': 'idle', 'anim_frame': 0, 'anim_timer': 0})
            obstacles.append(q_rect)

    # -------- 生成隐藏砖块（SMB1 原版 invisible ? block） --------
    # 策略：扫描所有砖块列的正上方 2-4 格空中空位，以 3% 概率放隐藏砖块
    global hidden_blocks
    if len(hidden_blocks) < MAX_HIDDEN_BLOCKS_PER_LEVEL:
        # 收集所有已用的 rect（blocks + obstacles + question_blocks + pipes）
        all_occupied = list(blocks) + list(obstacles) + [q['rect'] for q in question_blocks]
        for px in pipes:
            all_occupied.append(px)
        # 扫描每一列（BLOCK_SIZE 对齐）
        tried_cols = set()
        for rect in list(obstacles) + list(blocks):
            col = rect.x // BLOCK_SIZE
            if col in tried_cols or col < 8:  # 安全区跳过
                continue
            tried_cols.add(col)
            if random.random() > HIDDEN_BLOCK_SPAWN_CHANCE:
                continue
            # 尝试在该列 2-4 格高度放置
            for height_offset in (4, 3, 2):  # 先试更高的位置
                hb_y = start_y - height_offset * BLOCK_SIZE
                hb_rect = pygame.Rect(col * BLOCK_SIZE, hb_y, BLOCK_SIZE, BLOCK_SIZE)
                # 上方一格不能有阻挡（否则放不进去）
                above_rect = hb_rect.move(0, -BLOCK_SIZE)
                below_rect = hb_rect.move(0, BLOCK_SIZE)
                # 检查四邻是否被占（自身+上下+左右）
                neighbors_busy = False
                for check_rect in (hb_rect, above_rect, below_rect,
                                   hb_rect.move(BLOCK_SIZE, 0),
                                   hb_rect.move(-BLOCK_SIZE, 0)):
                    for occ in all_occupied:
                        if check_rect.colliderect(occ):
                            neighbors_busy = True
                            break
                    if neighbors_busy:
                        break
                if neighbors_busy:
                    continue
                # 生成内容：80% 金币，20% 1-Up 蘑菇
                content = '1up' if random.random() < 0.2 else 'coin'
                hidden_blocks.append({
                    'rect': hb_rect,
                    'state': 'hidden',    # 'hidden'=不绘制, 'revealed'=画 empty block
                    'content': content,
                    'anim_timer': 0
                })
                # 关键：加入 obstacles 使其成为实体（SMB1 原版行为——可以撞、可以站）
                obstacles.append(hb_rect)
                # 标记该列已用 + 计数已生成
                tried_cols.add(col)
                break  # 该列成功就停
            if len(hidden_blocks) >= MAX_HIDDEN_BLOCKS_PER_LEVEL:
                break


def start_death(mario, pit=False):
    global death_channel, death_wait_for_music
    global lives, death_screen_timer, death_screen_phase, game_over_channel
    global prev_world_str
    global invincible_timer, invincible_grace_timer, waiting_for_invincibility, timer_warning_channel
    if mario.dead:
        return
    # 大马里奥直接缩回（不走 morph，避免死亡时动画错乱）
    if mario.is_big or mario.morph_state != 'none':
        mario.is_big = False
        mario.is_crouch = False
        mario.morph_state = 'none'
        mario.sync_height(keep_bottom=True)
    # 保存当前关卡（用于 GAME OVER 时恢复）
    prev_world_str = WORLD_STR
    mario.dead = True
    mario.y_v = 0
    mario.on_ground = False
    mario.is_pit_death = pit
    # 使用不同的死亡动画常量
    if pit:
        mario.death_rise_frames = PIT_DEATH_RISE_FRAMES
        mario.death_pause = PIT_DEATH_PAUSE_FRAMES
        mario.death_rise_speed = PIT_DEATH_RISE_SPEED
    else:
        mario.death_rise_frames = DEATH_RISE_FRAMES
        mario.death_pause = DEATH_PAUSE_FRAMES
        mario.death_rise_speed = DEATH_RISE_SPEED
    # 清除无敌状态，避免死亡动画结束后仍保留无敌效果
    invincible_timer = 0
    invincible_grace_timer = 0
    waiting_for_invincibility = False
    # 停止无敌音乐（Sound通道循环播放，pygame.mixer.music.stop()无法停止）
    if invincibility_music:
        invincibility_music.stop()
    if timer_warning_channel:
        timer_warning_channel.stop()
        timer_warning_channel = None

    # 扣除命数（God Mode 不扣）
    if not GOD_MODE:
        lives -= 1
    if death_sound:
        channel = pygame.mixer.find_channel()
        if channel:
            channel.play(death_sound)
            death_channel = channel
            death_wait_for_music = True
        else:
            death_channel = None
            death_wait_for_music = False
    else:
        death_channel = None
        death_wait_for_music = False
    pygame.mixer.music.stop()


def spawn_enemies_in_segment(start_col, end_col):
    """在已生成的列范围内随机放置敌人，优先放在有地面的列上"""
    global goombas, koopas
    candidate_cols = []

    # 计算城堡位置，城堡前8格不刷怪
    end_castle_img = get_castle_img()
    castle_col = (world_width - end_castle_img.get_width() - BLOCK_SIZE) // BLOCK_SIZE if castle_spawned else (MAX_WORLD_WIDTH - end_castle_img.get_width() - BLOCK_SIZE) // BLOCK_SIZE
    enemy_safe_zone_start = castle_col - 8  # 城堡前8格不刷怪

    # 起点保护区（前START_SAFE_ZONE_COLS列不刷怪）
    start_safe_zone_end = START_SAFE_ZONE_COLS

    for col in range(start_col, end_col):
        # 在安全区域内不刷怪（包括起点保护区和终点保护区）
        if col >= enemy_safe_zone_start or col < start_safe_zone_end:
            continue

        ground_x = col * BLOCK_SIZE
        # 判断该列是否存在地面块（在 start_y 行）
        has_ground = any(b.x == ground_x and b.y == start_y for b in blocks)
        if has_ground:
            candidate_cols.append(col)

    if not candidate_cols:
        return

    # 生成少量敌人：每段最多 2 个，且 18 格内最多 2 个
    max_enemy_count = min(2, len(candidate_cols))
    enemy_count = random.randint(0, max_enemy_count)
    selected_cols = []
    shuffled_cols = candidate_cols[:]
    random.shuffle(shuffled_cols)
    for col in shuffled_cols:
        if len(selected_cols) >= enemy_count:
            break
        if any(abs(col - existing_col) <= 17 for existing_col in selected_cols):
            continue
        selected_cols.append(col)

    for col in selected_cols:
        x = col * BLOCK_SIZE + BLOCK_SIZE // 2
        # 50% 生成 Goomba，否则生成 Koopa
        if random.random() < 0.6:
            goombas.append(Goomba(x, start_y - GOOMBA_SIZE))
        else:
            direction = random.choice([-1, 1])
            koopas.append(KoopaTroopa(x, start_y - KOOPA_WALK_SIZE_H, direction))


def award_stomp_score(mario):
    """处理空中连踩计分并更新全局分数与生命。"""
    global score, lives
    ladder = [100, 200, 400, 800, 1000, 2000, 5000, 8000]
    if not getattr(mario, 'on_ground', False):
        mario.chain = getattr(mario, 'chain', 0) + 1
        if mario.chain <= len(ladder):
            pts = ladder[mario.chain - 1]
        else:
            pts = 8000
        score += pts
        # 每完成 8 次连踩奖励一命（8,16,24...）
        if mario.chain >= 8 and mario.chain % 8 == 0:
            lives += 1
    else:
        # 在地面踩或正常踩，不计入空中连击
        mario.chain = 0
        pts = 100
        score += pts
    return pts


def switch_to_fast_bgm():
    """暂停BGM，播放Timer-Warning，等待完成后再切换到加速版BGM"""
    global timer_warning_triggered, bgm_switched_to_fast, saved_bgm_position
    global timer_warning_channel, waiting_for_invincibility
    global waiting_for_warning_finish, pending_fast_bgm_position
    
    if bgm_switched_to_fast or not fast_bgm_available or waiting_for_warning_finish:
        return
    
    # 保存当前BGM播放位置（毫秒）
    try:
        saved_bgm_position = pygame.mixer.music.get_pos()
    except Exception:
        saved_bgm_position = 0
    
    # 计算加速版BGM的对应位置
    original_progress = saved_bgm_position / (ORIGINAL_BGM_DURATION * 1000)
    pending_fast_bgm_position = int(FAST_BGM_DURATION * 1000 * original_progress)
    
    # 暂停当前BGM
    pygame.mixer.music.pause()
    
    # 播放Timer-Warning音效
    if timer_warning_sound:
        timer_warning_channel = timer_warning_sound.play()
        waiting_for_warning_finish = True
    else:
        # 如果没有警告音效，直接切换
        _do_switch_to_fast_bgm()
    
    timer_warning_triggered = True
    waiting_for_invincibility = False


def _do_switch_to_fast_bgm():
    """实际执行BGM切换到加速版"""
    global bgm_switched_to_fast, pending_fast_bgm_position
    
    # 停止当前BGM并加载加速版
    pygame.mixer.music.stop()
    pygame.mixer.music.load(fast_bgm_file)
    pygame.mixer.music.play(-1, start=pending_fast_bgm_position / 1000.0)
    
    bgm_switched_to_fast = True


def restore_original_bgm():
    """恢复原始BGM（关卡重置时调用）"""
    global timer_warning_triggered, bgm_switched_to_fast, saved_bgm_position
    global timer_warning_channel, waiting_for_invincibility
    global waiting_for_warning_finish, pending_fast_bgm_position
    
    # 停止警告音效
    if timer_warning_channel:
        timer_warning_channel.stop()
        timer_warning_channel = None
    
    # 恢复原始BGM
    pygame.mixer.music.stop()
    pygame.mixer.music.load(background_music)
    pygame.mixer.music.play(-1)
    
    timer_warning_triggered = False
    bgm_switched_to_fast = False
    saved_bgm_position = 0
    waiting_for_invincibility = False
    waiting_for_warning_finish = False
    pending_fast_bgm_position = 0


def handle_timer_warning():
    """处理时间警告逻辑（每帧调用）"""
    global timer_warning_triggered, invincible_timer, waiting_for_invincibility, time_left
    global waiting_for_warning_finish, timer_warning_channel
    
    # 检查Timer-Warning是否播放完成
    if waiting_for_warning_finish:
        if timer_warning_channel is None or not timer_warning_channel.get_busy():
            # Timer-Warning播放完成，切换到加速版BGM
            _do_switch_to_fast_bgm()
            waiting_for_warning_finish = False
            timer_warning_channel = None
        return
    
    if not timer_warning_triggered and time_left < 100:
        # 如果在无敌星阶段（含宽限期），等待结束后再切换
        if invincible_timer > 0 or invincible_grace_timer > 0:
            waiting_for_invincibility = True
        else:
            switch_to_fast_bgm()
    
    # 如果在等待无敌星结束，且无敌星已结束
    if waiting_for_invincibility and invincible_timer <= 0 and invincible_grace_timer <= 0:
        switch_to_fast_bgm()


def draw_status_bar(screen, bg_color=None, top_padding=0):
    global time_left, time_frame_counter, coins, score
    STATUS_HEIGHT = STATUS_FONT_SIZE + 8
    # 背景条
    bar_rect = pygame.Rect(0, top_padding, WIDTH, STATUS_HEIGHT)
    if bg_color is None:
        bg_color = SKY_BLUE
    pygame.draw.rect(screen, bg_color, bar_rect)

    # 布局参数：左右边距和四等分列
    margin = 12
    inner_width = WIDTH - margin * 2
    col_w = inner_width / 4

    # helper: 居中绘制文本在指定列索引
    def blit_center_in_col(surf, img_surface, col_index, y):
        col_cx = margin + col_w * col_index + col_w / 2
        rect = img_surface.get_rect()
        rect.centerx = int(col_cx)
        rect.y = y
        surf.blit(img_surface, rect)

    # 列 0：MARIO 与分数（上下两行）
    left_label = status_font.render('MARIO', True, WHITE)
    score_label = status_font.render(f'{score:06d}', True, WHITE)
    blit_center_in_col(screen, left_label, 0, top_padding + 2)
    blit_center_in_col(screen, score_label, 0, top_padding + 2 + left_label.get_height())

    # 列 1：金币图标与数量（第一行为空行，第二行显示金币，与其他列对齐）
    coin_text = status_font.render(f'x{coins:02d}', True, WHITE)
    # 计算第二行的 Y 坐标（与 MARIO 分数行、WORLD 值行、TIME 值行对齐）
    row2_y = top_padding + 2 + left_label.get_height()
    if coin_frames_icon:
        icon_img = coin_frames_icon[0]
        total_w = icon_img.get_width() + 6 + coin_text.get_width()
        col_cx = margin + col_w * 1 + col_w / 2
        start_x = int(col_cx - total_w / 2)
        screen.blit(icon_img, (start_x, row2_y))
        screen.blit(coin_text, (start_x + icon_img.get_width() + 6, row2_y + 2))
    else:
        blit_center_in_col(screen, coin_text, 1, row2_y)

    # 列 2：WORLD（上下两行）
    world_label = status_font.render('WORLD', True, WHITE)
    world_val = status_font.render(WORLD_STR, True, WHITE)
    blit_center_in_col(screen, world_label, 2, top_padding + 2)
    blit_center_in_col(screen, world_val, 2, top_padding + 2 + world_label.get_height())

    # 列 3：TIME（上下两行）
    time_label = status_font.render('TIME', True, WHITE)
    time_val = status_font.render(f'{time_left}', True, WHITE)
    blit_center_in_col(screen, time_label, 3, top_padding + 2)
    blit_center_in_col(screen, time_val, 3, top_padding + 2 + time_label.get_height())

    # 计时器每 0.4 秒递减 1（仅在未死亡、非关卡介绍画面且非通关中时减少）
    time_frame_counter += 1
    if time_frame_counter >= FRAMES_PER_TIME_TICK:
        time_frame_counter = 0
        if time_left > 0 and 'mario' in globals() and not getattr(mario, 'dead', False) and not level_intro and pass_phase == 0:
            time_left -= 1
            if time_left <= 0:
                try:
                    start_death(mario)
                except Exception:
                    pass


def advance_world():
    """关卡递增：1-1→1-2→1-3→1-4→2-1→...→8-4，返回是否到达最终关"""
    global WORLD_STR
    parts = WORLD_STR.split('-')
    world = int(parts[0])
    stage = int(parts[1])
    if world == 8 and stage == 4:
        return True  # 已是最终关
    stage += 1
    if stage > 4:
        stage = 1
        world += 1
    WORLD_STR = f'{world}-{stage}'
    return False

def reset_game(inherit_is_big=False):
    """重置关卡/重开一局。inherit_is_big=True 时保留 Super Mario 状态（通关到下一关）"""
    global mario, camera_x, world_width, world_ended, blocks, goombas, koopas, obstacles, death_black_timer, death_wait_for_music, death_channel, time_left, time_frame_counter
    global castle_rect, castle_spawned, pass_timer, pass_channel, pass_phase, pass_mario_hidden, time_convert_step, time_to_convert
    global coins, score, coins_in_world
    global death_screen_timer, death_screen_phase, game_over_channel
    global WORLD_STR
    # 保存继承状态（在 Mario 对象被覆盖前读取）——必须放在 global mario 声明之后
    _prev_big = inherit_is_big and getattr(globals().get('mario', None), 'is_big', False)
    if not WORLD_STR:
        WORLD_STR = '1-1'
    global stars_in_world, star_generated_this_level, invincible_timer, invincible_grace_timer, pipes
    global fortress_rect, question_blocks, emerging_stars, mushrooms_in_world
    global bricks_broken
    bricks_broken = []   # 清理所有残留的破碎粒子
    global game_state, level_intro, high_score
    global session_level_cache, level_cache_max_col
    global timer_warning_triggered, bgm_switched_to_fast, saved_bgm_position
    global waiting_for_invincibility, timer_warning_channel
    global waiting_for_warning_finish, pending_fast_bgm_position
    # 管道进入相关重置
    global is_underground, pipe_enter_state, pipe_enter_timer, pipe_entry_pipes, _current_enter_pipe
    is_underground = False
    pipe_enter_state = 'none'
    pipe_enter_timer = 0
    _current_enter_pipe = None
    pipe_entry_pipes = []
    # 重置 BGM 回地表
    _switch_bgm(False)

    # 检查是否有当前关卡的缓存
    if WORLD_STR in session_level_cache:
        # 从缓存恢复地形（云、平台、坑、水管位置不变）
        restored = restore_level_from_cache(WORLD_STR)
        if restored is not False:
            restored_goombas, restored_koopas = restored
            # 恢复马里奥到起点
            mario = Mario(fortress_rect.centerx - MARIO_REAL_W // 2, start_y - MARIO_REAL_H, MARIO_REAL_W, MARIO_REAL_H)
            camera_x = 0
            # 恢复敌人（保留原位置，已死的敌人仍为死状态）
            goombas = restored_goombas if restored_goombas else [
                Goomba(600, start_y - GOOMBA_SIZE),
                Goomba(1200, start_y - GOOMBA_SIZE)
            ]
            koopas = restored_koopas
            # 重置分数和金币
            time_left = get_level_time_start(WORLD_STR)
            time_frame_counter = 0
            pass_timer = 0
            pass_channel = None
            pass_phase = 0
            pass_mario_hidden = False
            time_convert_step = 0
            time_to_convert = 0
            coins = 0
            score = 0
            # 重置无敌状态
            invincible_timer = 0
            invincible_grace_timer = 0
            stars_in_world = []
            mushrooms_in_world = []
            fire_flowers_in_world = []
            fireballs = []
            hidden_blocks = []  # 重置隐藏砖块（从缓存恢复或全新生成都应清空）
            question_blocks = []  # 缓存恢复时 question_blocks 也需要清空再由 restore 填充
            emerging_stars = []
            # 重置死亡画面状态
            death_screen_timer = 0
            death_screen_phase = 0
            game_over_channel = None
            level_intro = True
            game_state = 'intro'
            # 重置时间警告状态
            timer_warning_triggered = False
            bgm_switched_to_fast = False
            saved_bgm_position = 0
            waiting_for_invincibility = False
            waiting_for_warning_finish = False
            pending_fast_bgm_position = 0
            if timer_warning_channel:
                timer_warning_channel.stop()
                timer_warning_channel = None
            if os.path.exists(background_music):
                pygame.mixer.music.load(background_music)
                pygame.mixer.music.set_volume(0.5)
                pygame.mixer.music.play(-1)
            return

    # 没有缓存，使用原有随机生成逻辑
    world_width = INITIAL_WORLD_WIDTH
    world_ended = False
    blocks = []
    obstacles = []
    coins_in_world = []
    stars_in_world = []
    star_generated_this_level = False
    mushrooms_in_world = []
    fire_flowers_in_world = []
    fireballs = []
    question_blocks = []
    hidden_blocks = []  # 清空隐藏砖块
    emerging_stars = []
    invincible_timer = 0
    invincible_grace_timer = 0
    pipes = []
    # 根据关卡设置起点城堡
    start_fortress = get_fortress_img()
    fortress_rect = pygame.Rect(BLOCK_SIZE, start_y - start_fortress.get_height(), start_fortress.get_width(), start_fortress.get_height())
    generate_world_segment(0, world_width)
    goombas = [
        Goomba(600, start_y - GOOMBA_SIZE),
        Goomba(1200, start_y - GOOMBA_SIZE)
    ]
    # 重开时也仅产生蘑菇，乌龟后续通过地图扩展或段刷生成
    koopas = []
    mario = Mario(fortress_rect.centerx - MARIO_REAL_W // 2, start_y - MARIO_REAL_H, MARIO_REAL_W, MARIO_REAL_H)
    # 通关到下一关时，保留 Super Mario 状态（SMB1 原版行为）
    if _prev_big:
        mario.is_big = True
        mario.sync_height(keep_bottom=True)
        mario.facing = 'right'  # 重置方向
    camera_x = 0
    death_black_timer = 0
    death_wait_for_music = False
    death_channel = None
    # 重开时重置计时器
    time_left = get_level_time_start(WORLD_STR)
    time_frame_counter = 0
    # 重置通关状态
    castle_rect = pygame.Rect(0, 0, 0, 0)
    castle_spawned = False
    pass_timer = 0
    pass_channel = None
    pass_phase = 0
    pass_mario_hidden = False
    time_convert_step = 0
    time_to_convert = 0
    # 清空金币和积分
    coins = 0
    score = 0
    # 重置死亡画面状态
    death_screen_timer = 0
    death_screen_phase = 0
    game_over_channel = None
    # 显示关卡开始介绍画面
    level_intro = True
    game_state = 'intro'
    # 重置时间警告状态
    timer_warning_triggered = False
    bgm_switched_to_fast = False
    saved_bgm_position = 0
    waiting_for_invincibility = False
    waiting_for_warning_finish = False
    pending_fast_bgm_position = 0
    if timer_warning_channel:
        timer_warning_channel.stop()
        timer_warning_channel = None
    if os.path.exists(background_music):
        pygame.mixer.music.load(background_music)
        pygame.mixer.music.set_volume(0.5)
        pygame.mixer.music.play(-1)
    # 保存初始关卡布局到会话缓存
    save_level_to_cache()

def should_trigger_question_block_bump(mario, question_block):
    rect = question_block['rect']
    if question_block.get('state', 'idle') != 'idle':
        return False
    if mario.y_v >= 0:
        return False
    if not mario.rect.colliderect(rect):
        return False
    # 确保马里奥是在向上撞击，并且方块上下没有遮挡物（包括水管等 obstacles/pipes）
    rect_above = rect.move(0, -BLOCK_SIZE)
    rect_below = rect.move(0, BLOCK_SIZE)
    env_check = blocks + obstacles + pipes
    # 如果上方或下方存在遮挡物，则不允许触发顶开
    if any(rect_above.colliderect(r) for r in env_check):
        return False
    if any(rect_below.colliderect(r) for r in env_check):
        return False
    mario_left = mario.rect.left + 4
    mario_right = mario.rect.right - 4
    block_left = rect.left + 4
    block_right = rect.right - 4
    hit = mario_right > block_left and mario_left < block_right
    return hit


def update_question_block_states():
    global question_blocks, stars_in_world, emerging_stars
    for block in question_blocks[:]:
        state = block.get('state', 'idle')
        if state == 'opening':
            block['anim_timer'] += 1
            if block['anim_timer'] >= 3:
                block['anim_timer'] = 0
                block['anim_frame'] += 1
                if block['anim_frame'] >= len(question_block_frames):
                    block['anim_frame'] = len(question_block_frames) - 1 if question_block_frames else 0
                    block['state'] = 'opened'
        elif state == 'opened':
            block['anim_frame'] = len(question_block_frames) - 1 if question_block_frames else 0
        elif state == 'idle':
            if question_block_frames:
                block['anim_timer'] += 1
                if block['anim_timer'] >= 8:
                    block['anim_timer'] = 0
                    block['anim_frame'] = (block.get('anim_frame', 0) + 1) % len(question_block_frames)
            else:
                block['anim_frame'] = 0

    for star in emerging_stars[:]:
        if star.get('rise_frames', 0) > 0:
            star['rect'].y -= 4
            star['rise_frames'] -= 1
        else:
            stars_in_world.append({
                'rect': pygame.Rect(star['rect'].x, star['rect'].y, COIN_WORLD_SIZE, COIN_WORLD_SIZE),
                'frame': 0,
                'timer': 0,
                'x_v': 3,
                'y_v': 0,
            })
            emerging_stars.remove(star)

    # ---------- Super Mushroom 物理更新 ----------
    env_blocks = blocks + obstacles + pipes
    for msh in mushrooms_in_world[:]:
        # 先执行弹出动画（rise_frames 阶段）
        if msh.get('rise_frames', 0) > 0:
            msh['rect'].y -= 3
            msh['rise_frames'] -= 1
            if msh['rise_frames'] <= 0:
                msh['rise_frames'] = 0  # 标记为已弹出
        else:
            # 重力
            msh['y_v'] = min(msh['y_v'] + GRAVITY, 15)
            msh['rect'].y += msh['y_v']
            msh['on_ground'] = False
            # 垂直碰撞（落地/碰顶）
            for blk in env_blocks:
                if msh['rect'].colliderect(blk):
                    # 从上方落下 → 落地
                    if msh['y_v'] > 0 and msh['rect'].bottom - msh['y_v'] <= blk.top + 1:
                        msh['rect'].bottom = blk.top
                        msh['y_v'] = 0
                        msh['on_ground'] = True
                    # 向上弹到天花板
                    elif msh['y_v'] < 0 and msh['rect'].top - msh['y_v'] >= blk.bottom - 1:
                        msh['rect'].top = blk.bottom
                        msh['y_v'] = 0
            # 水平移动（弹出结束后才开始滑）
            msh['rect'].x += msh['x_v']
            for blk in env_blocks:
                if msh['rect'].colliderect(blk):
                    if msh['x_v'] > 0:
                        msh['rect'].right = blk.left
                    elif msh['x_v'] < 0:
                        msh['rect'].left = blk.right
                    msh['x_v'] = -msh['x_v']
                    break
        # 掉出屏幕底部
        if msh['rect'].top > HIGH + 100:
            mushrooms_in_world.remove(msh)

    # ---------- Fire Flower 物理更新（只弹出，不移动） ----------
    for ff in fire_flowers_in_world[:]:
        if ff.get('rise_frames', 0) > 0:
            ff['rect'].y -= 3
            ff['rise_frames'] -= 1
        # 掉出屏幕底部
        if ff['rect'].top > HIGH + 100:
            fire_flowers_in_world.remove(ff)

# ---------- 辅助：probe 真正遮挡检测 ----------
# pygame.Rect.collidelist 包含边界相交，但我们只关心真正有面积重叠的
def probe_is_blocked(probe, env_blocks):
    for blk in env_blocks:
        if probe.colliderect(blk):
            overlap = probe.clip(blk)
            if overlap.width > 0 and overlap.height > 0:
                return True
    return False

# 砖块破碎粒子已在文件前部定义（BrickPiece 类 + bricks_broken 列表）

class Mario(pygame.sprite.Sprite):
    SPRITES = load_sprite_sheets('MainCharacters', 'Mario', MARIO_SPRITE_W, MARIO_SPRITE_H, MARIO_REAL_W, MARIO_REAL_H, True)
    JUMP_FRAME_RIGHT = pygame.transform.scale(pygame.image.load(asset_path("assets", "MainCharacters", "Mario", "jump.png")).convert_alpha(), (MARIO_REAL_W, MARIO_REAL_H))
    JUMP_FRAME_LEFT = pygame.transform.flip(JUMP_FRAME_RIGHT, True, False)

    def __init__(self, x, y, width, height, x_v=0):
        super().__init__()
        self.rect = pygame.Rect(x, y, width, height)
        self.speedx = SPEEDX
        self.animation_count = 0
        self.frame_timer = 0
        self.facing = "right"
        self.is_moving = False
        self.sprite = None
        self.x_v = x_v
        self.y_v = 0
        self.on_ground = False
        self.dead = False
        self.death_pause = 0
        self.death_rise_frames = 0
        self.can_jump = True
        # 计分与连击计数（空中连踩）
        self.chain = 0
        self.score = 0
        # 变大/下蹲状态（SMB1 原版设计）
        self.is_big = False
        self.is_crouch = False  # 仅在 is_big 时有效
        self.fire_mode = False  # Fire Mario 状态（可发射火球）
        self.fire_cooldown = 0  # 火球射击冷却帧数
        # 变大/下蹲碰撞盒实际高度
        self.small_h = MARIO_REAL_H          # 48
        self.big_h = BIG_MARIO_REAL_H        # 96
        self.crouch_h = CROUCH_REAL_H        # 66 (22*3) SMB1 NES 原版蹲姿高
        # Morph 变形动画状态机
        self.morph_state = 'none'            # 'none' | 'growing' | 'shrinking'
        self.morph_frame = 0
        self.morph_timer = 0
        self.morph_speed = 6                 # 每帧停留的 tick 数 (10帧 × 6 = 60帧 ≈ 1 秒)

    # -------- 动态尺寸 --------
    def real_height(self):
        if self.is_big and self.is_crouch:
            return self.crouch_h
        if self.is_big:
            return self.big_h
        return self.small_h

    def sync_height(self, keep_bottom=True):
        """让 rect.height 与 real_height() 对齐，保持底部位置不变（脚下对齐）"""
        h = self.real_height()
        if keep_bottom:
            self.rect.y = self.rect.bottom - h
        self.rect.height = h
        self.rect.width = self.small_h  # 宽度始终 48

    # -------- Morph 状态机 --------
    def start_grow(self):
        """开始小→大 morph 动画（期间保持小碰撞盒，最后一帧才切换）"""
        if self.is_big or self.morph_state != 'none':
            return False
        # 上方遮挡检查（忽略边界接触，只算真正重叠）
        env = blocks + obstacles + pipes
        new_top = self.rect.bottom - self.big_h
        probe = pygame.Rect(self.rect.left, new_top, self.rect.width, self.big_h - self.rect.height)
        if probe_is_blocked(probe, env):
            return False
        # 播放变大音效（SMB1 Power-Up）
        if power_up_sound:
            try:
                power_up_sound.play()
            except Exception:
                pass
        self.morph_state = 'growing'
        self.morph_frame = 0
        self.morph_timer = 0
        self.x_v = 0
        self.y_v = 0
        return True

    def start_shrink(self):
        """开始大→小 morph 动画：立即缩回碰撞盒（防二次碰撞），动画结束才真正切状态"""
        if not self.is_big or self.morph_state != 'none':
            return
        # Fire Mario 被撞 → 先退回 Big Mario（不掉小）
        if self.fire_mode:
            self.fire_mode = False
            self.update_sprite()
            return
        # 播放变小音效（SMB1 Power-Down / Oof）
        if power_down_sound:
            try:
                power_down_sound.play()
            except Exception:
                pass
        self.morph_state = 'shrinking'
        self.morph_frame = len(MORPH_FRAMES) - 1  # 从最后一帧倒放
        self.morph_timer = 0
        self.is_crouch = False
        self.sync_height(keep_bottom=True)
        self.x_v = 0
        self.y_v = 0

    def advance_morph(self):
        """推进 morph 动画一帧；返回 True 表示动画进行中"""
        if self.morph_state == 'none':
            return False
        self.morph_timer += 1
        if self.morph_timer >= self.morph_speed:
            self.morph_timer = 0
            if self.morph_state == 'growing':
                self.morph_frame += 1
                if self.morph_frame >= len(MORPH_FRAMES):
                    # grow 完成：切大尺寸
                    self.is_big = True
                    self.sync_height(keep_bottom=True)
                    self.morph_state = 'none'
                    return False
            else:  # shrinking
                self.morph_frame -= 1
                if self.morph_frame < 0:
                    # shrink 完成：切小尺寸
                    self.is_big = False
                    self.sync_height(keep_bottom=True)
                    self.morph_state = 'none'
                    return False
        return True

    # -------- 变大/缩回（旧接口保留给蘑菇碰撞，但已改为触发 morph） --------
    def grow(self):
        """吃蘑菇入口：触发 growing morph"""
        return self.start_grow()

    def shrink(self):
        """被怪撞入口：触发 shrinking morph"""
        self.start_shrink()

    # -------- 下蹲 --------
    def start_crouch(self):
        if self.is_big and self.on_ground and not self.is_crouch and self.morph_state == 'none':
            self.is_crouch = True
            self.sync_height(keep_bottom=True)
            self.x_v = 0  # 下蹲时不能移动

    def end_crouch(self):
        if self.is_big and self.is_crouch and self.morph_state == 'none':
            env = blocks + obstacles + pipes
            h_big = self.big_h
            new_top = self.rect.bottom - h_big
            probe = pygame.Rect(self.rect.left, new_top, self.rect.width, h_big - self.rect.height)
            if probe_is_blocked(probe, env):
                return  # 被顶头，站不起来
            self.is_crouch = False
            self.sync_height(keep_bottom=True)

    # -------- 精灵选择 --------
    def update_sprite(self):
        if self.dead:
            self.sprite = death_mario_img
            return
        # morph 动画优先（底部对齐绘制，rect.height 期间可能还是 48 或 96）
        if self.morph_state != 'none':
            frames = MORPH_FRAMES if self.facing == "right" else MORPH_FRAMES_LEFT
            if frames and 0 <= self.morph_frame < len(frames):
                self.sprite = frames[self.morph_frame]
            return
        # 下蹲状态
        if self.is_big and self.is_crouch:
            if self.fire_mode:
                self.sprite = _fire_crouch_right if self.facing == "right" else _fire_crouch_left
            else:
                self.sprite = BIG_CROUCH_RIGHT if self.facing == "right" else BIG_CROUCH_LEFT
            return
        # 跳跃
        if not self.on_ground:
            if self.is_big:
                if self.fire_mode:
                    self.sprite = _fire_jump_right if self.facing == "right" else _fire_jump_left
                else:
                    self.sprite = BIG_JUMP_RIGHT if self.facing == "right" else BIG_JUMP_LEFT
            else:
                self.sprite = self.JUMP_FRAME_RIGHT if self.facing == "right" else self.JUMP_FRAME_LEFT
            return
        # 行走动画
        keys = pygame.key.get_pressed()
        is_sprinting = (keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]) and self.is_moving
        anim_speed = ANIM_SPEED // 2 if is_sprinting else ANIM_SPEED
        self.frame_timer += 1
        if self.frame_timer >= anim_speed:
            self.frame_timer = 0
            self.animation_count += 1
        if self.is_big:
            if self.fire_mode:
                frames = _fire_run_frames_right if self.facing == "right" else _fire_run_frames_left
                if self.x_v == 0 or not frames:
                    self.sprite = _fire_idle_right if self.facing == "right" else _fire_idle_left
                else:
                    idx = self.animation_count % len(frames)
                    self.sprite = frames[idx]
            else:
                frames = BIG_RUN_FRAMES_RIGHT if self.facing == "right" else BIG_RUN_FRAMES_LEFT
                if self.x_v == 0 or not frames:
                    self.sprite = BIG_IDLE_RIGHT if self.facing == "right" else BIG_IDLE_LEFT
                else:
                    idx = self.animation_count % len(frames)
                    self.sprite = frames[idx]
        else:
            state = "run" if self.x_v != 0 else "idle"
            sprite_key = f"{state}_{self.facing}"
            sprites = self.SPRITES.get(sprite_key, [])
            if len(sprites) == 0:
                return
            sprite_index = self.animation_count % len(sprites)
            self.sprite = sprites[sprite_index]

    def draw(self, screen, camera_x=0):
        if self.sprite:
            draw_x = self.rect.x - camera_x
            # morph 动画 sprite 固定 48×96，期间 rect.height 可能是 48 或 96，必须底部对齐
            if self.morph_state != 'none':
                draw_y = self.rect.bottom - self.sprite.get_height()
            else:
                draw_y = self.rect.y
            # 无敌状态：彩虹闪烁特效（只覆盖精灵的有色像素，不覆盖透明背景）
            if invincible_timer > 0:
                rainbow_colors = [
                    (255, 0, 0),     # 红
                    (255, 127, 0),   # 橙
                    (255, 255, 0),   # 黄
                    (0, 255, 0),     # 绿
                    (0, 0, 255),     # 蓝
                    (75, 0, 130),    # 靛
                    (148, 0, 211),   # 紫
                ]
                color_index = (pygame.time.get_ticks() // 50) % len(rainbow_colors)
                tint_color = rainbow_colors[color_index]
                
                # 最后3秒开始闪烁滤镜淡出
                alpha = 120
                if invincible_timer <= INVINCIBILITY_GRACE * 3:
                    # 每0.1秒闪烁一次
                    blink = (pygame.time.get_ticks() // 100) % 2
                    alpha = 120 if blink == 0 else 40
                
                # 先绘制原始精灵
                screen.blit(self.sprite, (draw_x, draw_y))
                # 在其上叠加半透明彩虹色层（使用 mask 确保只覆盖有色像素）
                spr_w, spr_h = self.sprite.get_width(), self.sprite.get_height()
                overlay = pygame.Surface((spr_w, spr_h), pygame.SRCALPHA)
                overlay.fill(tint_color + (alpha,))
                # 使用 sprite 的 mask 清除透明区域
                sprite_mask = pygame.mask.from_surface(self.sprite)
                for x in range(spr_w):
                    for y in range(spr_h):
                        if not sprite_mask.get_at((x, y)):
                            overlay.set_at((x, y), (0, 0, 0, 0))
                screen.blit(overlay, (draw_x, draw_y))
            else:
                screen.blit(self.sprite, (draw_x, draw_y))

class Goomba(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.rect = pygame.Rect(x, y, GOOMBA_SIZE, GOOMBA_SIZE)
        self.dead = False
        self.shell_killed = False
        self.sprite = goomba_walk_frames[0]
        self.frame_index = 0
        self.frame_timer = 0
        self.dead_timer = 0
        self.speed_x = -1.5
        self.shell_x_v = 0
        self.y_v = 0
        self.frozen = False  # God Mode: 冻结敌人

    def die(self, shell=False, direction=1):
        if self.dead or self.shell_killed:
            return
        if shell:
            self.shell_killed = True
            self.shell_x_v = GOOMBA_SHELL_KILL_BOUNCE_SPEED * direction
            self.y_v = -abs(self.y_v) if self.y_v != 0 else JUMP_POWER / 1.5
            self.dead_timer = 0
            self.sprite = goomba_dead2_img
            return
        self.dead = True
        self.dead_timer = 0
        bottom = self.rect.bottom
        self.rect.height = GOOMBA_SIZE // 2
        self.rect.y = bottom - self.rect.height
        self.sprite = goomba_dead_img

    def update(self, block_list):
        # God Mode: 冻结敌人 → 跳过所有运动/重力
        if self.frozen and not self.shell_killed and not self.dead:
            return
        if self.shell_killed:
            self.y_v += GRAVITY
            self.rect.y += self.y_v
            self.rect.x += self.shell_x_v
            if self.rect.top > HIGH:
                self.dead = True
                self.shell_killed = False
            return
        if self.dead:
            self.dead_timer += 1
            return
        self.rect.x += self.speed_x
        for blk in block_list:
            if self.rect.colliderect(blk):
                if self.speed_x < 0:
                    self.rect.left = blk.right
                else:
                    self.rect.right = blk.left
                self.speed_x *= -1
                break
        self.frame_timer += 1
        if self.frame_timer >= 10:
            self.frame_timer = 0
            self.frame_index = (self.frame_index + 1) % len(goomba_walk_frames)
            self.sprite = goomba_walk_frames[self.frame_index]

        self.y_v += GRAVITY
        self.rect.y += self.y_v
        self.on_ground = False
        for blk in block_list:
            if self.rect.colliderect(blk):
                if self.y_v > 0:
                    self.rect.bottom = blk.top
                    self.y_v = 0
                    self.on_ground = True
                elif self.y_v < 0:
                    self.rect.top = blk.bottom
                    self.y_v = 0

        # 掉坑死亡
        if self.rect.top > HIGH:
            self.dead = True

    def draw(self, screen, camera_x=0):
        # 地下场景：根据状态用对应 palette 的 sprite
        if is_underground:
            if self.shell_killed:
                spr = goomba_dead2_img_underground
            elif self.dead:
                spr = goomba_dead_img_underground
            else:
                frames = goomba_walk_frames_underground
                f_idx = self.frame_index % len(frames) if frames else 0
                spr = frames[f_idx]
        else:
            spr = self.sprite
        screen.blit(spr, (self.rect.x - camera_x, self.rect.y))


class KoopaTroopa(pygame.sprite.Sprite):
    def __init__(self, x, y, direction=-1):
        super().__init__()
        self.direction = direction
        self.initial_direction = direction
        self.state = "walk"
        self.walk_frames_right = koopa_sheet_right
        self.walk_frames_left = koopa_sheet_left
        self.shell_img = koopa_shell_img
        self.frame_timer = 0
        self.frame_index = 0
        self.y_v = 0
        self.on_ground = False
        self.dead = False
        self.shell_timer = 0
        self.has_been_kicked = False
        # 将乌龟的碰撞箱缩小到与蘑菇/Goomba 相同，避免卡墙
        hit_h = GOOMBA_SIZE
        hit_w = GOOMBA_SIZE
        # 输入 y 是精灵顶点位置（通常为 start_y - KOOPA_WALK_SIZE_H）
        # 调整 y 使碰撞箱底部与原精灵底部对齐
        adj_y = y + (KOOPA_WALK_SIZE_H - hit_h)
        self.rect = pygame.Rect(x, adj_y, hit_w, hit_h)
        self.speed_x = KOOPA_WALK_SPEED * self.direction
        self.sprite = self.walk_frames_right[0] if self.direction > 0 else self.walk_frames_left[0]
        self.frozen = False

    def update_sprite(self):
        if self.state == "walk":
            self.frame_timer += 1
            if self.frame_timer >= 10:
                self.frame_timer = 0
                self.frame_index = (self.frame_index + 1) % len(self.walk_frames_right)
            if self.direction > 0:
                self.sprite = self.walk_frames_right[self.frame_index]
            else:
                self.sprite = self.walk_frames_left[self.frame_index]
            return
        self.sprite = self.shell_img

    def stomp(self):
        if self.dead or self.state != "walk":
            return
        bottom = self.rect.bottom
        self.state = "shell_static"
        self.has_been_kicked = False
        self.shell_timer = KOOPA_SHELL_RESTORE_FRAMES
        self.rect.height = KOOPA_SHELL_SIZE_H
        self.rect.bottom = bottom
        self.y_v = 0
        self.speed_x = 0
        self.sprite = self.shell_img

    def kick(self, direction):
        if self.dead or self.state != "shell_static":
            return
        self.state = "shell_slide"
        self.has_been_kicked = True
        self.direction = direction
        self.speed_x = KOOPA_SHELL_SPEED * self.direction
        self.sprite = self.shell_img

    def resurrect(self):
        if self.dead:
            return
        bottom = self.rect.bottom
        self.state = "walk"
        self.direction = self.initial_direction
        self.rect.height = KOOPA_WALK_SIZE_H
        self.rect.bottom = bottom
        self.speed_x = KOOPA_WALK_SPEED * self.direction
        self.frame_index = 0
        self.frame_timer = 0
        self.sprite = self.walk_frames_right[0] if self.direction > 0 else self.walk_frames_left[0]
        self.has_been_kicked = False
        self.shell_timer = 0

    def die(self):
        self.dead = True

    def update(self, block_list, goombas, koopas):
        if self.dead:
            return
        # God Mode: 冻结敌人
        if self.frozen and self.state == "walk":
            return
        if self.state == "walk":
            self.speed_x = KOOPA_WALK_SPEED * self.direction
        elif self.state == "shell_slide":
            self.speed_x = KOOPA_SHELL_SPEED * self.direction
        else:
            self.speed_x = 0

        self.rect.x += self.speed_x
        for blk in block_list:
            if self.rect.colliderect(blk):
                if self.speed_x < 0:
                    self.rect.left = blk.right
                else:
                    self.rect.right = blk.left
                self.direction *= -1
                self.speed_x = abs(self.speed_x) * self.direction
                break

        if self.state == "shell_slide":
            for goomba in goombas[:]:
                if self.rect.colliderect(goomba.rect) and not goomba.dead and not goomba.shell_killed:
                    goomba.die(shell=True, direction=self.direction)
                    if goomba_death_sound:
                        goomba_death_sound.play()
            for other in koopas[:]:
                if other is not self and not other.dead and self.rect.colliderect(other.rect):
                    other.die()

        self.y_v += GRAVITY
        self.rect.y += self.y_v
        self.on_ground = False
        for blk in block_list:
            if self.rect.colliderect(blk):
                if self.y_v > 0:
                    self.rect.bottom = blk.top
                    self.y_v = 0
                    self.on_ground = True
                elif self.y_v < 0:
                    self.rect.top = blk.bottom
                    self.y_v = 0

        if self.state == "shell_static" and self.on_ground and not self.has_been_kicked:
            self.shell_timer -= 1
            if self.shell_timer <= 0:
                self.resurrect()

        if self.rect.top > HIGH:
            self.dead = True

    def draw(self, screen, camera_x=0):
        # 地下场景：用蓝色 palette 的 Koopa
        if is_underground and self.state == "walk":
            if self.direction > 0:
                frames = koopa_sheet_right_underground
            else:
                frames = koopa_sheet_left_underground
            f_idx = self.frame_index % len(frames) if frames else 0
            spr = frames[f_idx]
        elif is_underground and self.state in ("shell_static", "shell_slide"):
            spr = koopa_shell_img_underground
        else:
            spr = self.sprite
        # 将精灵底部对齐到碰撞箱底部，并水平居中
        spr_w, spr_h = spr.get_width(), spr.get_height()
        draw_x = self.rect.x - camera_x - max(0, (spr_w - self.rect.width) // 2)
        draw_y = self.rect.bottom - spr_h
        screen.blit(spr, (draw_x, draw_y))


def mario_move(mario, block_list):
    global question_blocks, emerging_stars, coins, star_generated_this_level, invincible_timer, invincible_grace_timer, score
    global pipe_enter_state, pipe_enter_timer, is_underground, _current_enter_pipe, fireballs, pipes, goombas, koopas
    global _prev_touch_jump
    # Morph 动画期间：冻结所有输入/物理，只推进动画帧
    if mario.morph_state != 'none':
        mario.is_moving = False
        mario.x_v = 0
        mario.y_v = 0
        mario.advance_morph()
        return
    keys = pygame.key.get_pressed()
    # 触控模式：优先从 touch_input 字典读取
    if TOUCH_MODE:
        move_dir = touch_input['move_x']
        mario.is_moving = (move_dir != 0)
        if move_dir == -1: mario.facing = "left"
        elif move_dir == 1: mario.facing = "right"
        # action 按钮 = 加速（Ctrl 兼容）
        target_speed = SPEEDX * SPRINT_MULTIPLIER if touch_input['action'] else SPEEDX
    else:
        move_dir = 0
        mario.is_moving = False
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            move_dir = -1
            mario.facing = "left"
            mario.is_moving = True
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            move_dir = 1
            mario.facing = "right"
            mario.is_moving = True
        target_speed = SPEEDX
        if keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]:
            target_speed = SPEEDX * SPRINT_MULTIPLIER

    if move_dir != 0:
        if mario.x_v * move_dir < 0:
            mario.x_v = 0
        if abs(mario.x_v) < target_speed:
            mario.x_v += move_dir * RUN_ACCEL
            if abs(mario.x_v) > target_speed:
                mario.x_v = move_dir * target_speed
        elif abs(mario.x_v) > target_speed:
            mario.x_v -= move_dir * RUN_DECEL
            if abs(mario.x_v) < target_speed:
                mario.x_v = move_dir * target_speed
    else:
        if mario.x_v > 0:
            mario.x_v = max(0, mario.x_v - RUN_DECEL)
        elif mario.x_v < 0:
            mario.x_v = min(0, mario.x_v + RUN_DECEL)

    # ========== Fire Mario 火球发射 ==========
    if mario.fire_mode and not mario.dead and pipe_enter_state == 'none':
        # 冷却递减
        if mario.fire_cooldown > 0:
            mario.fire_cooldown -= 1
        # 攻击键（Z / X / J / Shift / 触控 action 按钮）射击
        attack_pressed = (touch_input['action'] if TOUCH_MODE else False) or \
            keys[pygame.K_z] or keys[pygame.K_x] or keys[pygame.K_j] or \
            keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        if attack_pressed and mario.fire_cooldown <= 0:
            _shoot_dir = 1 if mario.facing == "right" else -1
            _fb_x = mario.rect.centerx + _shoot_dir * (MARIO_REAL_W // 2)
            _fb_y = mario.rect.centery - 4
            fireballs.append({
                'rect': pygame.Rect(_fb_x - 12, _fb_y - 12, 24, 24),
                'x_v': 8 * _shoot_dir,
                'y_v': -3,  # 初始轻微上抛
                'bounces': 0,
                'alive': True,
                'frame_timer': 0,
            })
            mario.fire_cooldown = 30  # 0.5秒冷却

    # ========== 管道进入地下 ==========
    # 按↓键 / 触控 DOWN 按钮 + 站在可进入管道口 → 触发进入动画
    crouch_keys = keys[pygame.K_s] or keys[pygame.K_DOWN] or (touch_input['crouch'] if TOUCH_MODE else False)
    _on_top_of_pipe = False
    _found_pipe = None
    for pe_pipe in pipe_entry_pipes:
        _h_overlap = (mario.rect.right > pe_pipe.left + 4 and mario.rect.left < pe_pipe.right - 4)
        _v_diff = abs(mario.rect.bottom - pe_pipe.top)
        if _h_overlap and _v_diff <= 6:
            _on_top_of_pipe = True
            _found_pipe = pe_pipe
            break
    if pipe_enter_state == 'none' and crouch_keys and _on_top_of_pipe and not mario.dead:
        # 触发进入！保存当前进入的管道
        _current_enter_pipe = _found_pipe
        try:
            if pipe_enter_sound: pipe_enter_sound.play()
        except Exception: pass
        pipe_enter_state = 'entering'
        pipe_enter_timer = 0
        mario.is_moving = False
        mario.x_v = 0

    # ========== 管道进入动画 + 地下切换 ==========
    # SMB1 原版：管道吞掉马里奥（无淡入淡出，硬切地下）
    _ENTER_SINK_FRAMES = 30   # 马里奥下沉帧数（被管道吞掉）
    _ENTER_RISE_FRAMES = 30   # 马里奥上升帧数（从地下管道冒头）
    if pipe_enter_state != 'none':
        pipe_enter_timer += 1
        if pipe_enter_state == 'entering':
            if pipe_enter_timer <= _ENTER_SINK_FRAMES:
                # 阶段 1：马里奥慢速下沉（管道绘制在马里奥上方遮挡，视觉上被管道吞掉）
                mario.y_v = max(mario.y_v, 1)
            elif pipe_enter_timer == _ENTER_SINK_FRAMES + 1:
                # 硬切：切换地下状态 + BGM
                is_underground = not is_underground
                _switch_bgm(is_underground)
                # 将马里奥放到当前管道口上方（准备"冒头"）
                if _current_enter_pipe:
                    mario.rect.top = _current_enter_pipe.top - MARIO_REAL_H
                mario.y_v = 0
            elif pipe_enter_timer <= _ENTER_SINK_FRAMES + 1 + _ENTER_RISE_FRAMES:
                # 阶段 2：马里奥慢速上移（从管道口冒出来）
                mario.y_v = min(mario.y_v, -1)
            else:
                # 完成
                pipe_enter_state = 'none'
                pipe_enter_timer = 0
                _current_enter_pipe = None
                mario.y_v = 0
        elif pipe_enter_state == 'exiting':
            pass

    # 下蹲输入（仅变大后生效）
    if pipe_enter_state == 'none':  # 动画期间冻结输入
        if crouch_keys and not mario.on_ground:
            # 空中按↓加速下落
            mario.y_v = max(mario.y_v, 8)
        elif crouch_keys and mario.is_big and mario.on_ground:
            mario.start_crouch()
        elif not crouch_keys and mario.is_big and mario.is_crouch:
            mario.end_crouch()

    # 记录移动前水平位置，用于区分水平碰撞与垂直碰撞
    prev_left = mario.rect.left
    prev_right = mario.rect.right
    prev_top = mario.rect.top
    prev_bottom = mario.rect.bottom
    mario.rect.x += mario.x_v
    mario.rect.left = max(0, mario.rect.left)
    # 限制马里奥不能超出窗口左边界
    mario.rect.left = max(camera_x, mario.rect.left)

    # 水平碰撞检测：如果刚才水平移动导致与方块相交，且之前不在方块内，按水平方向修正
    if not mario.dead and mario.x_v != 0:
        for blk in block_list:
            if mario.rect.colliderect(blk):
                if mario.x_v > 0 and prev_right <= blk.left:
                    mario.rect.right = blk.left
                    mario.x_v = 0
                elif mario.x_v < 0 and prev_left >= blk.right:
                    mario.rect.left = blk.right
                    mario.x_v = 0
    # 限制 Mario 不走出当前世界边界
    if mario.rect.right > world_width:
        mario.rect.right = world_width
        mario.x_v = 0
    # ====== 触控跳跃（边沿 + 落地自动复位 _prev，保证按住连跳） ======
    if TOUCH_MODE and game_state in ('playing', 'intro'):
        global _prev_touch_jump
        # 落地时强制清零 _prev_jump → 下帧 jump=True 就有新上升沿
        if mario.on_ground and _prev_touch_jump:
            _prev_touch_jump = False
        if touch_input['jump'] and not _prev_touch_jump and mario.on_ground:
            if mario.is_crouch:
                mario.end_crouch()
            mario.y_v = JUMP_POWER
            if jump_sound: jump_sound.play()
            _prev_touch_jump = True
        elif not touch_input['jump']:
            _prev_touch_jump = False
    mario.y_v += GRAVITY
    mario.rect.y += mario.y_v
    mario.on_ground = False
    if not mario.dead:
        for question_block in question_blocks:
            if should_trigger_question_block_bump(mario, question_block):
                # 立即切换为“打开中”状态并将帧设为已被顶的造型，使视觉上瞬间变为被顶后的样式
                question_block['state'] = 'opening'
                question_block['anim_frame'] = (len(question_block_frames) - 1) if question_block_frames else 0
                question_block['anim_timer'] = 0
                # 产出优先级：star > mushroom > coin
                is_star_reward = star_frames and (not star_generated_this_level) and (WORLD_STR == '1-3' or random.random() < 0.03)
                if is_star_reward:
                    if question_block_open_sound:
                        question_block_open_sound.play()
                    mario.y_v = int(JUMP_POWER * 0.35)
                    mario.on_ground = False
                    emerging_stars.append({
                        'rect': pygame.Rect(question_block['rect'].x + 2, question_block['rect'].bottom - COIN_WORLD_SIZE + 2, COIN_WORLD_SIZE, COIN_WORLD_SIZE),
                        'frame': 0,
                        'timer': 0,
                        'rise_frames': 14,
                        'y_v': 0,
                    })
                    star_generated_this_level = True
                elif super_mushroom_img and random.random() < MUSHROOM_SPAWN_CHANCE:
                    # Super Mushroom / Fire Flower：大马里奥时出 Fire Flower，小马里奥时出蘑菇
                    if question_block_open_sound:
                        question_block_open_sound.play()
                    mario.y_v = 0
                    mario.rect.top = question_block['rect'].bottom
                    mario.on_ground = False
                    if mario.is_big and fire_flower_img:
                        # Fire Flower：从砖块内部弹出来，停在砖块正上方一格（SMB1 原版行为）
                        fire_flowers_in_world.append({
                            'rect': pygame.Rect(
                                question_block['rect'].x + (BLOCK_SIZE - MARIO_REAL_W) // 2,
                                question_block['rect'].bottom - MARIO_REAL_W,  # 砖块内底部
                                MARIO_REAL_W, MARIO_REAL_W),
                            'rise_frames': 16,  # 16×3=48px 刚好弹到砖块顶部上方
                        })
                    else:
                        mushrooms_in_world.append({
                            'rect': pygame.Rect(question_block['rect'].x + 4, question_block['rect'].top - MARIO_REAL_W, MARIO_REAL_W, MARIO_REAL_W),
                            'rise_frames': 18,   # 弹出高度
                            'x_v': 2,            # 向右滑
                            'y_v': 0,
                            'on_ground': False,
                        })
                else:
                    coins += 1
                    # 不播放问号方块 Open 音效，金币静默生成，Mario 保持在方块下方
                    mario.y_v = 0
                    mario.rect.top = question_block['rect'].bottom
                    mario.on_ground = False
                    try:
                        if gold_sound:
                            gold_sound.play()
                    except Exception:
                        pass
                    coin_rect = pygame.Rect(question_block['rect'].x + (BLOCK_SIZE - COIN_WORLD_SIZE) // 2,
                                             question_block['rect'].y - COIN_WORLD_SIZE,
                                             COIN_WORLD_SIZE, COIN_WORLD_SIZE)
                    coins_in_world.append({'rect': coin_rect, 'frame': 0, 'timer': 0, 'collecting': True, 'rise_frames': int(FPS * 0.25), 'y_v': 0})
                break

        # -------- 隐藏砖块（SMB1 原版 invisible ? block）顶部碰撞 --------
        for hb in hidden_blocks:
            if hb['state'] != 'hidden':
                continue  # 已显现的隐藏砖块不再触发
            if mario.y_v < 0 and mario.rect.colliderect(hb['rect']):
                # 显形：加入 bumped_blocks 播放弹起动画
                hb['state'] = 'revealed'
                hb['anim_timer'] = 0
                if question_block_open_sound:
                    try: question_block_open_sound.play()
                    except Exception: pass
                mario.y_v = int(JUMP_POWER * 0.35)
                mario.on_ground = False
                bumped_blocks[id(hb['rect'])] = {'rect': hb['rect'], 't': 0, 'max_t': max(4, int(FPS * 0.18))}
                # 根据内容生成物品
                if hb['content'] == '1up':
                    # 1-Up 蘑菇（用 Super Mushroom 的图，但 score 加 1000，lives + 1）
                    if super_mushroom_img:
                        mushrooms_in_world.append({
                            'rect': pygame.Rect(hb['rect'].x + 4, hb['rect'].top - MARIO_REAL_W, MARIO_REAL_W, MARIO_REAL_W),
                            'rise_frames': 18,
                            'x_v': 2,
                            'y_v': 0,
                            'on_ground': False,
                            'is_1up': True
                        })
                    try:
                        lives += 1
                        score += 1000
                        if power_up_sound:
                            power_up_sound.play()
                    except Exception: pass
                else:  # coin
                    # 生成一个静默上升的金币（和问号砖块的 coin 逻辑一样）
                    try:
                        if gold_sound: gold_sound.play()
                    except Exception: pass
                    coin_rect = pygame.Rect(hb['rect'].x + (BLOCK_SIZE - COIN_WORLD_SIZE) // 2,
                                             hb['rect'].y - COIN_WORLD_SIZE,
                                             COIN_WORLD_SIZE, COIN_WORLD_SIZE)
                    coins_in_world.append({'rect': coin_rect, 'frame': 0, 'timer': 0, 'collecting': True, 'rise_frames': int(FPS * 0.25), 'y_v': 0})
                mario.rect.top = hb['rect'].bottom
                break

        # -------- 重写：先收集要处理的块，循环完统一处理 --------
        _blocks_to_break = []   # 大马里奥顶碎的块
        _blocks_to_push = []    # 小马里奥弹的块
        for blk in block_list:
            if mario.y_v < 0 and mario.rect.colliderect(blk):
                # 忽略问号砖块（在 opening 状态时已经在上面处理过了）
                if any(q['rect'] == blk for q in question_blocks):
                    continue
                # 忽略已显现的隐藏砖块（用 empty ? block 表现，不能被大马里奥顶碎）
                if any(hb['state'] != 'hidden' and hb['rect'] == blk for hb in hidden_blocks):
                    continue
                # 防重复：同一块只处理一次
                if blk in _blocks_to_break or blk in _blocks_to_push:
                    continue
                if mario.is_big:
                    _blocks_to_break.append(blk)
                else:
                    _blocks_to_push.append(blk)

        # 大马里奥顶碎所有命中的砖块（统一处理，防 8 粒子 bug）
        if _blocks_to_break:
            # 只播放一次破碎音效（不管碎几块）
            if break_block_sound:
                try: break_block_sound.play()
                except Exception: pass
            # 弹一下（SMB1 原版：大马里奥顶碎后有轻微反弹）
            mario.y_v = int(JUMP_POWER * 0.35)
            mario.on_ground = False
            for blk in _blocks_to_break:
                # 生成 4 块带真实贴图的碎片
                slices = _make_brick_pieces(blk)
                if slices and len(slices) == 4:
                    cx = blk.centerx - slices[0].get_width() // 2
                    cy = blk.centery - slices[0].get_height() // 2
                    bricks_broken.append(BrickPiece(blk.left, blk.top, slices[0], vx=-3.5, vy=-5.0, rotating=True))
                    bricks_broken.append(BrickPiece(cx + slices[1].get_width(), blk.top, slices[1], vx=3.5, vy=-5.0, rotating=True))
                    bricks_broken.append(BrickPiece(blk.left, cy + slices[2].get_height(), slices[2], vx=-3.5, vy=-2.0, rotating=True))
                    bricks_broken.append(BrickPiece(cx + slices[3].get_width(), cy + slices[3].get_height(), slices[3], vx=3.5, vy=-2.0, rotating=True))
                # 从 blocks 和 obstacles 里同时删（防止 blk 来自 obstacles 删不到）
                for pool in (blocks, obstacles):
                    for b in list(pool):
                        if b is blk or (hasattr(b, 'x') and b.x == blk.x and b.y == blk.y and b.width == blk.width and b.height == blk.height):
                            try: pool.remove(b)
                            except ValueError: pass
                            break
                score += 50

        # 小马里奥弹所有命中的块（顶回 + 播放 hit_block_sound + 方块弹起动画）
        for blk in _blocks_to_push:
            mario.rect.top = blk.bottom
            mario.y_v = 0
            # 上方无遮挡时，播放 hit_block_sound 并让方块弹一下
            rect_above = blk.move(0, -BLOCK_SIZE)
            env = blocks + obstacles
            if not any(rect_above.colliderect(r) for r in env):
                bid = id(blk)
                if bid not in bumped_blocks:
                    bumped_blocks[bid] = {'rect': blk, 't': 0, 'max_t': max(4, int(FPS * 0.18))}
                    try:
                        if hit_block_sound:
                            hit_block_sound.play()
                    except Exception:
                        pass
        # 处理普通地面/障碍碰撞，但跳过刚刚被顶开的问号砖块
        for blk in block_list:
            # 管道进入动画期间跳过当前进入管道的碰撞（让马里奥能"钻进/钻出"管道）
            if pipe_enter_state != 'none' and _current_enter_pipe is not None and blk is _current_enter_pipe:
                continue
            is_question_block = False
            for q in question_blocks:
                # 仅在刚被顶开的短时 "opening" 状态下跳过该块的碰撞检测，避免被顶时卡住。
                # 打开完成（'opened'）后该方块仍然参与碰撞检测，避免出现可穿透问题。
                if q['rect'] == blk and q.get('state', 'idle') == 'opening':
                    is_question_block = True
                    break
            if is_question_block:
                continue
            if mario.rect.colliderect(blk):
                if mario.y_v > 0:
                    # 向下移动并碰撞到地面
                    mario.rect.bottom = blk.top
                    mario.y_v = 0
                    mario.on_ground = True
                    mario.chain = 0
                    break
                elif mario.y_v < 0:
                    # 向上移动并撞到头部
                    mario.rect.top = blk.bottom
                    mario.y_v = 0
                    break
    # 允许向上跳出屏幕，移除顶部限制

# 生成初始地图块以确保开局有地面
generate_world_segment(0, world_width)

goombas = [
    Goomba(600, start_y - GOOMBA_SIZE),
    Goomba(1200, start_y - GOOMBA_SIZE)
]
# 开局不生成乌龟，之后地图延展时可能刷出
koopas = []
mario = Mario(fortress_rect.centerx - MARIO_REAL_W // 2, start_y - MARIO_REAL_H, MARIO_REAL_W, MARIO_REAL_H)
camera_x = 0
running = True
current_fps = 0.0
death_black_timer = 0
paused = False
focus_paused = False

def tick_and_update_fps():
    global current_fps
    delta_ms = clock.tick(FPS)
    current_fps = 1000.0 / delta_ms if delta_ms > 0 else 0.0
    return delta_ms

try:
    icon_raw = pygame.image.load(asset_path('assets', 'MainCharacters', 'Mario', 'jump.png')).convert_alpha()
    icon_scaled = pygame.transform.scale(icon_raw, (MARIO_REAL_W, MARIO_REAL_H))
    pygame.display.set_icon(icon_scaled)
except:
    pass

# 设置 Windows 任务栏图标（WM_SETICON）
try:
    import win32gui
    import win32con
    icon_path = os.path.abspath(asset_path('assets', 'icon.ico'))
    if os.path.exists(icon_path):
        hwnd = pygame.display.get_wm_info()['window']
        hicon = win32gui.LoadImage(0, icon_path, win32con.IMAGE_ICON, 0, 0, win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE)
        if hicon:
            win32gui.SendMessage(hwnd, win32con.WM_SETICON, win32con.ICON_BIG, hicon)
            win32gui.SendMessage(hwnd, win32con.WM_SETICON, win32con.ICON_SMALL, hicon)
        else:
            print("错误：图标加载失败，hicon 为空")
except Exception as e:
    print(f"设置任务栏图标时出错：{e}")

while running:
    for event in pygame.event.get():
        # 触控模式下：把事件转给触控处理（MOUSE* 和 FINGER*）
        if TOUCH_MODE and event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP,
                                          pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
            _handle_touch_events(event)
        if event.type == pygame.QUIT:
            running = False
            break
        if event.type == pygame.ACTIVEEVENT:
            if event.state == 2:
                prev_focus = window_focus
                window_focus = bool(event.gain)
                # 失去焦点时自动暂停，恢复焦点时自动恢复（仅恢复由失焦触发的暂停）
                if not window_focus and not paused:
                    focus_paused = True
                    paused = True
                    try:
                        if pause_sound:
                            pause_sound.play()
                    except Exception:
                        pass
                    try:
                        pygame.mixer.music.pause()
                    except Exception:
                        pass
                    if invincibility_music and invincible_timer > 0:
                        try:
                            invincibility_music.stop()
                        except Exception:
                            pass
                elif window_focus and focus_paused:
                    focus_paused = False
                    paused = False
                    if invincible_timer > 0:
                        if invincibility_music:
                            invincibility_music.play(-1)
                    else:
                        try:
                            pygame.mixer.music.unpause()
                        except Exception:
                            pass
        if game_state == 'title':
            # 标题页鼠标/触控点击菜单项
            if TOUCH_MODE and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                menu_y_base = logo_y + logo_img.get_height() + 60
                menu_gap = STATUS_FONT_SIZE + 25
                menu_items_click = ['1 PLAYER GAME', 'RESHUFFLE THE MAP']
                for idx, item in enumerate(menu_items_click):
                    item_y = menu_y_base + idx * menu_gap
                    item_text = status_font.render(item, True, WHITE)
                    text_x = WIDTH // 2 - item_text.get_width() // 2
                    if (text_x <= mx <= text_x + item_text.get_width() and
                        item_y - 5 <= my <= item_y + STATUS_FONT_SIZE + 5):
                        title_menu_index = idx
                        if idx == 0:
                            game_state = 'intro'
                            reset_game()
                        else:
                            session_level_cache.clear()
                            level_cache_max_col.clear()
                            blocks.clear(); obstacles.clear(); coins_in_world.clear()
                            stars_in_world.clear(); question_blocks.clear(); hidden_blocks.clear()
                            emerging_stars.clear(); pipes.clear(); goombas.clear(); koopas.clear()
                            mushrooms_in_world.clear(); world_width = INITIAL_WORLD_WIDTH
                            random.seed()
                            reshuffle_hint_timer = 3 * FPS
                            reshuffle_hint_text = 'MAP SHUFFLED!'
                        break
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    title_menu_index = (title_menu_index - 1) % 2
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    title_menu_index = (title_menu_index + 1) % 2
                elif event.key == pygame.K_RETURN:
                    if title_menu_index == 0:
                        # 选择 1 PLAYER GAME，开始游戏
                        game_state = 'intro'
                        # 确保游戏状态正确初始化
                        reset_game()
                    else:
                        # RESHUFFLE THE MAP：清理关卡缓存，地图将重新随机生成
                        session_level_cache.clear()
                        level_cache_max_col.clear()
                        # 清理残留实体，确保下次 reset_game() 重新生成
                        blocks.clear()
                        obstacles.clear()
                        coins_in_world.clear()
                        stars_in_world.clear()
                        question_blocks.clear()
                        hidden_blocks.clear()
                        emerging_stars.clear()
                        pipes.clear()
                        goombas.clear()
                        koopas.clear()
                        mushrooms_in_world.clear()
                        world_width = INITIAL_WORLD_WIDTH
                        # 每次 reshuffle 换一个随机种子，保证地图不同
                        random.seed()
                        reshuffle_hint_timer = 3 * FPS  # 显示 3 秒
                        reshuffle_hint_text = 'MAP SHUFFLED!'
                elif event.key == pygame.K_n:
                    # 恢复到死亡前的关卡
                    game_state = 'intro'
                    lives = 3
                    WORLD_STR = prev_world_str
                    is_final_world = False
                    reset_game()
            continue
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_r:
                can_restart_now = (game_state == 'title') or (
                    (not mario.dead and death_screen_phase == 0) or
                    death_screen_phase in (2, 3)
                )
                if can_restart_now:
                    reset_game()
            if event.key == pygame.K_p:
                paused = not paused
                if paused:
                    if pause_sound:
                        pause_sound.play()
                    # 暂停BGM
                    pygame.mixer.music.pause()
                    if invincibility_music and invincible_timer > 0:
                        invincibility_music.stop()
                else:
                    # 恢复BGM
                    if invincible_timer > 0:
                        if invincibility_music:
                            invincibility_music.play(-1)
                    else:
                        pygame.mixer.music.unpause()
            if event.key == pygame.K_n:
                lives = 3
                WORLD_STR = prev_world_str
                is_final_world = False
                reset_game()
            if event.key in (pygame.K_w, pygame.K_UP, pygame.K_SPACE):
                if mario.on_ground and not mario.dead and mario.can_jump:
                    # 原版 SMB1：蹲下时按跳 → 先站起来再跳
                    if mario.is_crouch:
                        mario.end_crouch()  # 尝试站起；如果头顶有东西挡着会自动失败
                        if mario.is_crouch:
                            # 被顶住站不起来 → 不跳
                            pass
                        else:
                            mario.y_v = JUMP_POWER
                            mario.can_jump = False
                            if jump_sound:
                                jump_sound.play()
                    else:
                        mario.y_v = JUMP_POWER
                        mario.can_jump = False
                        if jump_sound:
                            jump_sound.play()
        if event.type == pygame.KEYUP:
            if event.key in (pygame.K_w, pygame.K_UP, pygame.K_SPACE):
                mario.can_jump = True
    # ======== God Mode 调试快捷键（边沿触发，防长按） ========
    # 所有按键避开 WASD/方向键/Space/Z/X/J/Shift/Ctrl/N/R/P 等基础操作
    if GOD_MODE:
        _cur = pygame.key.get_pressed()
        _prev = globals().get('_prev_debug_keys', {})
        def _pressed(k):
            return _cur[k] and not _prev.get(k, False)
        # --- 关卡/传送 ---
        if _pressed(pygame.K_BACKQUOTE):  # ~ 键：瞬移到关卡末尾城堡
            mario.rect.x = world_width - BLOCK_SIZE - 10
            mario.on_ground = True
            print("[GOD] 瞬移: 关卡末尾")
        if _pressed(pygame.K_F5):  # 传送回出生点
            reset_game()
            print("[GOD] 传送: 出生点")
        if _pressed(pygame.K_F6):  # 模拟通关 → 下一关
            coins += 100
            reset_game(inherit_is_big=True)
            print("[GOD] 跳到下一关")
        # --- 形态切换 ---
        if _pressed(pygame.K_1):
            mario.fire_mode = False; mario.is_big = False
            print("[GOD] 形态: 小马里奥")
        if _pressed(pygame.K_2):
            mario.fire_mode = False; mario.is_big = True
            print("[GOD] 形态: 大马里奥")
        if _pressed(pygame.K_3):
            mario.fire_mode = True; mario.is_big = True
            print("[GOD] 形态: 火焰马里奥")
        if _pressed(pygame.K_F9):  # F9: 火焰 + 无敌星
            invincible_timer = 900
            invincible_grace_timer = FPS
            mario.fire_mode = True
            print("[GOD] 火焰 + 15秒无敌星")
        # --- 无敌 ---
        if _pressed(pygame.K_u):  # U: 切换永久无敌
            _inv = not getattr(mario, '_god_invincible', False)
            mario._god_invincible = _inv
            mario.invincible_timer = 999999 if _inv else 0
            print(f"[GOD] 永久无敌: {'ON' if _inv else 'OFF'}")
        # --- 敌人 ---
        if _pressed(pygame.K_F2):  # F2: 清空敌人列表
            goombas.clear(); koopas.clear()
            print("[GOD] 清屏所有敌人")
        if _pressed(pygame.K_F10):  # F10: 冻结/解冻敌人
            _freeze = not globals().get('_god_freeze_enemies', False)
            globals()['_god_freeze_enemies'] = _freeze
            for _g in goombas: _g.frozen = _freeze
            for _k in koopas: _k.frozen = _freeze
            print(f"[GOD] 敌人冻结: {'ON' if _freeze else 'OFF'}")
        # --- 资源 ---
        if _pressed(pygame.K_F11):  # F11: +50 coins, +5000 score
            coins += 50; score += 5000
            print(f"[GOD] +50 coins, +5000 score")
        if _pressed(pygame.K_F12):  # F12: +3 lives
            lives += 3
            print(f"[GOD] +3 lives (lives={lives})")
        # --- 调试显示 ---
        if _pressed(pygame.K_F3):  # F3: 碰撞盒描边
            _bx = not globals().get('_debug_show_boxes', False)
            globals()['_debug_show_boxes'] = _bx
            print(f"[GOD] 碰撞盒显示: {'ON' if _bx else 'OFF'}")
        if _pressed(pygame.K_F4):  # F4: Debug 状态信息
            _di = not globals().get('_debug_info', False)
            globals()['_debug_info'] = _di
            print(f"[GOD] Debug 信息: {'ON' if _di else 'OFF'}")
        # 更新前一帧状态
        _keys_watch = [
            pygame.K_BACKQUOTE, pygame.K_u,
            pygame.K_F2, pygame.K_F3, pygame.K_F4, pygame.K_F5,
            pygame.K_F6, pygame.K_F9, pygame.K_F10, pygame.K_F11, pygame.K_F12,
            pygame.K_1, pygame.K_2, pygame.K_3,
        ]
        globals()['_prev_debug_keys'] = {k: _cur[k] for k in _keys_watch}
    ime_force_english(window_focus)

    # 标题界面
    if game_state == 'title':
        # 确保标题界面的 IME 强制切换在焦点恢复时执行
        ime_force_english(window_focus)
        
        if window_focus:
            title_blink_timer += 1
        if reshuffle_hint_timer > 0:
            reshuffle_hint_timer -= 1
        
        screen.fill(SKY_BLUE)
        # 先绘制插画（底部）
        illustration_y = HIGH - ILLUSTRATION_H
        screen.blit(illustration_img, (0, illustration_y))
        # 顶部状态栏（在插画之上）
        draw_status_bar(screen, top_padding=STATUS_BAR_TOP_PADDING)
        # 绘制Logo（菜单栏下方，不碰到菜单栏）
        logo_x = WIDTH // 2 - logo_img.get_width() // 2
        logo_y = STATUS_BAR_TOP_PADDING + STATUS_FONT_SIZE + 8 + 50
        screen.blit(logo_img, (logo_x, logo_y))
        # 菜单文字区域
        menu_y = logo_y + logo_img.get_height() + 60
        menu_gap = STATUS_FONT_SIZE + 25  # 两个选项的垂直间距
        menu_items = ['1 PLAYER GAME', 'RESHUFFLE THE MAP']
        # 渲染菜单项（带动态蘑菇指示器）
        for idx, item in enumerate(menu_items):
            item_y = menu_y + idx * menu_gap
            item_text = status_font.render(item, True, WHITE)
            # 选中项闪烁菜单文字
            is_selected = (idx == title_menu_index)
            show_item = (not is_selected) or (title_blink_timer // 30 % 2 == 0)
            if show_item:
                screen.blit(item_text, (WIDTH // 2 - item_text.get_width() // 2, item_y))
            # 蘑菇指示器始终跟随选中项
            if is_selected:
                indicator_x = WIDTH // 2 - item_text.get_width() // 2 - SELECT_INDICATOR_W - 5
                indicator_y = item_y + STATUS_FONT_SIZE - SELECT_INDICATOR_H
                screen.blit(select_indicator_img, (indicator_x, indicator_y))
        # TOP 最高分（在 RESHUFFLE 选项下方）
        top_y = menu_y + len(menu_items) * menu_gap + 15
        top_label = status_font.render('TOP-', True, WHITE)
        top_score = status_font.render(f'{high_score:06d}', True, WHITE)
        top_total_w = top_label.get_width() + 10 + top_score.get_width()
        top_x = WIDTH // 2 - top_total_w // 2
        screen.blit(top_label, (top_x, top_y))
        screen.blit(top_score, (top_x + top_label.get_width() + 10, top_y))
        # RESHUFFLE 成功提示
        if reshuffle_hint_timer > 0:
            hint_alpha = 255
            hint_color = (255, 255, 80) if reshuffle_hint_timer > FPS else (255, 200, 80)
            hint_text = status_font.render(reshuffle_hint_text, True, hint_color)
            hint_y = top_y + STATUS_FONT_SIZE + 40
            screen.blit(hint_text, (WIDTH // 2 - hint_text.get_width() // 2, hint_y))
        
        # 失焦时显示暂停覆盖层
        if not window_focus:
            pause_font_size = int(STATUS_FONT_SIZE * 1.5)
            try:
                pause_font = pygame.font.Font(STATUS_FONT_PATH, pause_font_size)
            except Exception:
                pause_font = pygame.font.SysFont(None, pause_font_size)
            pause_text = pause_font.render('PAUSED', True, (255, 255, 0))
            bottom_margin = 60
            screen.blit(pause_text, (WIDTH // 2 - pause_text.get_width() // 2, HIGH - pause_text.get_height() - bottom_margin))
        
        pygame.display.update()
        tick_and_update_fps()
        continue
    # 关卡开始介绍画面
    if level_intro:
        pygame.mixer.music.pause()
        screen.fill((0, 0, 0))
        draw_status_bar(screen, bg_color=(0, 0, 0), top_padding=STATUS_BAR_TOP_PADDING)
        world_text = status_font.render(f'WORLD {WORLD_STR}', True, WHITE)
        screen.blit(world_text, (WIDTH // 2 - world_text.get_width() // 2, HIGH // 2 - 80))
        mario_x = WIDTH // 2 - 60
        mario_y = HIGH // 2 - 20
        screen.blit(death_screen_mario, (mario_x, mario_y))
        times_text = status_font.render(f'x {lives}', True, WHITE)
        screen.blit(times_text, (mario_x + MARIO_REAL_W + 10, mario_y + 10))
        pygame.display.update()
        death_screen_timer += 1
        if death_screen_timer > 90:
            level_intro = False
            game_state = 'playing'
            death_screen_timer = 0
            pygame.mixer.music.unpause()
        tick_and_update_fps()
        continue
    # 暂停逻辑
    if paused:
        # 绘制暂停文字（缩小、黄色、屏幕下方）
        pause_font_size = int(STATUS_FONT_SIZE * 1.5)
        try:
            pause_font = pygame.font.Font(STATUS_FONT_PATH, pause_font_size)
        except Exception:
            pause_font = pygame.font.SysFont(None, pause_font_size)
        pause_text = pause_font.render('PAUSED', True, (255, 255, 0))
        bottom_margin = 60
        screen.blit(pause_text, (WIDTH // 2 - pause_text.get_width() // 2, HIGH - pause_text.get_height() - bottom_margin))
        pygame.display.update()
        tick_and_update_fps()
        continue
    # ====== 触控跳跃（按住连跳）——移到 mario_move 内部和键盘同步 ======
    if window_focus and not mario.dead:
        mario_move(mario, blocks + obstacles)
    mario.update_sprite()

    if mario.rect.right > world_width - WIDTH and not world_ended:
        extend_world_to(world_width + WIDTH)

    camera_x = max(camera_x, mario.rect.right - WIDTH // 2)
    camera_x = max(camera_x, 0)
    # 限制摄像机不超过世界边界
    max_cam_x = max(0, world_width - WIDTH)
    if camera_x > max_cam_x:
        camera_x = max_cam_x

    # 每帧更新被顶方块的动画计时器，确保即使不在可视区域也能完成动画周期
    for bid in list(bumped_blocks.keys()):
        state = bumped_blocks.get(bid)
        if not state:
            continue
        state['t'] += 1
        if state['t'] > state['max_t']:
            try:
                del bumped_blocks[bid]
            except KeyError:
                pass

    # 如果直接掉出屏幕底部且还没触发死亡，判定为掉坑死亡（抬升高）
    if not mario.dead and pass_phase == 0 and mario.rect.top > HIGH:
        start_death(mario, pit=True)

    # 死亡画面：黑屏 + WORLD  + Mario × 命数
    if death_screen_phase == 1:
        screen.fill((0, 0, 0))
        draw_status_bar(screen, bg_color=(0, 0, 0), top_padding=STATUS_BAR_TOP_PADDING)
        # WORLD 文字
        world_text = status_font.render(f'WORLD {WORLD_STR}', True, WHITE)
        screen.blit(world_text, (WIDTH // 2 - world_text.get_width() // 2, HIGH // 2 - 80))
        # Mario 精灵 × 命数（水平排列）
        mario_x = WIDTH // 2 - 60
        mario_y = HIGH // 2 - 20
        screen.blit(death_screen_mario, (mario_x, mario_y))
        # 在马里奥图标和命数之间添加乘号
        times_text = status_font.render(f'x {lives}', True, WHITE)
        screen.blit(times_text, (mario_x + MARIO_REAL_W + 10, mario_y + 10))
        pygame.display.update()
        death_screen_timer += 1
        # 等待约1.5秒后检查命数
        if death_screen_timer > 90:
            if pass_settlement:
                # 通关结算
                pass_settlement = False
                if is_final_world:
                    # 8-4通关，进入胜利页面
                    death_screen_phase = 3
                    death_screen_timer = 0
                else:
                    # 通关到下一关，继承 is_big（SMB1 原版行为）
                    reset_game(inherit_is_big=True)
            elif lives <= 0:
                # 进入 GAME OVER
                death_screen_phase = 2
                death_screen_timer = 0
                if game_over_sound:
                    game_over_channel = game_over_sound.play()
            else:
                reset_game()
        tick_and_update_fps()
        continue

    # GAME OVER 画面
    if death_screen_phase == 2:
        screen.fill((0, 0, 0))
        # GAME OVER 文字
        go_font_size = int(STATUS_FONT_SIZE * 1.5)
        try:
            go_font = pygame.font.Font(STATUS_FONT_PATH, go_font_size)
        except Exception:
            go_font = pygame.font.SysFont(None, go_font_size)
        go_text = go_font.render('GAME OVER', True, WHITE)
        screen.blit(go_text, (WIDTH // 2 - go_text.get_width() // 2, HIGH // 2 - go_text.get_height() // 2))
        pygame.display.update()
        death_screen_timer += 1
        # 等待音效播放完 + 0.5秒后返回标题界面
        sound_done = (game_over_channel is None) or (not game_over_channel.get_busy())
        if sound_done and death_screen_timer > 30:
            # 更新最高分
            if score > high_score:
                high_score = score
                save_high_score(high_score)
            # 停止BGM并返回标题界面
            pygame.mixer.music.stop()
            lives = 3
            WORLD_STR = ''
            is_final_world = False
            score = 0
            coins = 0
            game_state = 'title'
            death_screen_phase = 0
            death_screen_timer = 0
        tick_and_update_fps()
        continue

    # 胜利画面（8-4通关）
    if death_screen_phase == 3:
        screen.fill((0, 0, 0))
        # 胜利文字
        win_font_size = int(STATUS_FONT_SIZE * 2)
        try:
            win_font = pygame.font.Font(STATUS_FONT_PATH, win_font_size)
        except Exception:
            win_font = pygame.font.SysFont(None, win_font_size)
        win_text = win_font.render('YOU WIN!', True, (255, 215, 0))
        screen.blit(win_text, (WIDTH // 2 - win_text.get_width() // 2, HIGH // 2 - 60))
        # 显示最终分数
        score_text = status_font.render(f'FINAL SCORE: {score:06d}', True, WHITE)
        screen.blit(score_text, (WIDTH // 2 - score_text.get_width() // 2, HIGH // 2 + 20))
        # 提示重开
        hint_text = status_font.render('Press R to Restart', True, WHITE)
        screen.blit(hint_text, (WIDTH // 2 - hint_text.get_width() // 2, HIGH // 2 + 120))
        pygame.display.update()
        death_screen_timer += 1
        # 保存最高分
        if score > high_score:
            high_score = score
            save_high_score(high_score)
        # 等待2秒后允许按R重开，或自动返回标题
        if death_screen_timer > 120:
            keys = pygame.key.get_pressed()
            if keys[pygame.K_r]:
                lives = 3
                WORLD_STR = ''
                is_final_world = False
                reset_game()
            elif keys[pygame.K_RETURN]:
                # 按Enter返回标题界面
                pygame.mixer.music.stop()
                lives = 3
                WORLD_STR = ''
                is_final_world = False
                score = 0
                coins = 0
                game_state = 'title'
                death_screen_phase = 0
                death_screen_timer = 0
        tick_and_update_fps()
        continue

    if death_black_timer > 0:
        # 先绘制菜单栏，然后填充下方为黑色
        draw_status_bar(screen, top_padding=STATUS_BAR_TOP_PADDING)
        STATUS_HEIGHT = STATUS_FONT_SIZE + 8
        black_rect = pygame.Rect(0, STATUS_HEIGHT, WIDTH, HIGH - STATUS_HEIGHT)
        pygame.draw.rect(screen, (0, 0, 0), black_rect)
        pygame.display.update()
        death_black_timer -= 1
        if death_black_timer == 0:
            reset_game()
        tick_and_update_fps()
        continue
    # 地下/地表背景色切换
    _bg_color = UNDERGROUND_BG_COLOR if is_underground else SKY_BLUE
    screen.fill(_bg_color)
    # 地下模式不绘制云朵（没有蓝天）
    if not is_underground:
        # 绘制云朵
        for cloud in clouds:
            draw_rect = cloud['rect'].move(-camera_x, 0)
            if draw_rect.right >= 0 and draw_rect.left <= WIDTH:
                screen.blit(cloud['img'], draw_rect)
    # 顶部状态栏（地下模式用深灰背景）
    _status_bg = UNDERGROUND_BG_COLOR if is_underground else SKY_BLUE
    try:
        draw_status_bar(screen, bg_color=_status_bg, top_padding=STATUS_BAR_TOP_PADDING)
    except NameError:
        pass
    for b in blocks:
        draw_rect = b.move(-camera_x, 0)
        if draw_rect.right >= 0 and draw_rect.left <= WIDTH:
            # 如果该方块处于被顶动画状态，则绘制时向上偏移（正弦平滑）
            bid = id(b)
            if bid in bumped_blocks:
                state = bumped_blocks[bid]
                t = state['t']
                max_t = state['max_t']
                # 计算偏移：减小为最高四分之一格，采用正弦过渡
                offset = int((BLOCK_SIZE // 4) * math.sin(math.pi * t / max_t))
                draw_rect = draw_rect.move(0, -offset)
                # 更新计时
                # 计时由主循环统一更新以确保在不可见时也能完成
            screen.blit(block_img_underground if is_underground else block_img, draw_rect)
    for ob in obstacles:
        draw_rect = ob.move(-camera_x, 0)
        if draw_rect.right >= 0 and draw_rect.left <= WIDTH:
            # 如果该障碍物处于被顶动画状态，则绘制时向上偏移（与 blocks 相同的视觉效果）
            bid = id(ob)
            if bid in bumped_blocks:
                state = bumped_blocks[bid]
                t = state['t']
                max_t = state['max_t']
                offset = int((BLOCK_SIZE // 4) * math.sin(math.pi * t / max_t))
                draw_rect = draw_rect.move(0, -offset)
                # 计时由主循环统一更新以确保在不可见时也能完成
            # Check if this obstacle is a pipe
            if ob in pipes:
                # 管道进入动画期间：管道稍后画（画在马里奥上面遮挡下沉）
                if pipe_enter_state != 'none':
                    continue
                screen.blit(pipe_img, draw_rect)
            else:
                screen.blit(block_img_underground if is_underground else obstacle_img, draw_rect)

    # 更新问号砖块状态
    update_question_block_states()

    # 绘制正在从问号砖块中冒出的无敌星（先画，问号砖块会遮挡它们）
    for star in emerging_stars[:]:
        draw_rect = star['rect'].move(-camera_x, 0)
        if draw_rect.right >= 0 and draw_rect.left <= WIDTH:
            frm = star['frame'] % len(star_frames)
            screen.blit(star_frames[frm], draw_rect)
            star['frame'] = (star['frame'] + 1) % len(star_frames)

    # 更新并绘制问号砖块
    _qb_frames = question_block_frames_underground if is_underground and question_block_frames_underground else question_block_frames
    _empty_img = empty_block_img_underground if is_underground else empty_block_img
    _brick_img = block_img_underground if is_underground else block_img
    for qblock in question_blocks[:]:
        draw_rect = qblock['rect'].move(-camera_x, 0)
        if draw_rect.right >= 0 and draw_rect.left <= WIDTH:
            if qblock.get('state', 'idle') == 'opened':
                screen.blit(_empty_img, draw_rect)
            elif _qb_frames:
                frame_idx = min(qblock.get('anim_frame', 0), len(_qb_frames) - 1)
                screen.blit(_qb_frames[frame_idx], draw_rect)
            else:
                screen.blit(_brick_img, draw_rect)

    # 绘制隐藏砖块（hidden 状态 God Mode 下半透明可见，revealed 正常画 empty block）
    for hb in hidden_blocks:
        draw_rect = hb['rect'].move(-camera_x, 0)
        if draw_rect.right < 0 or draw_rect.left > WIDTH:
            continue
        if hb['state'] == 'hidden':
            if GOD_MODE:
                # God Mode：半透明问号砖块轮廓 + 实心色提示
                _alpha_overlay = pygame.Surface((draw_rect.width, draw_rect.height), pygame.SRCALPHA)
                _color = (255, 215, 0, 80) if hb.get('content') == '1up' else (255, 255, 0, 80)
                pygame.draw.rect(_alpha_overlay, _color, _alpha_overlay.get_rect())
                pygame.draw.rect(_alpha_overlay, (255, 255, 255, 120), _alpha_overlay.get_rect(), 2)
                screen.blit(_alpha_overlay, draw_rect)
            continue
        draw_rect = hb['rect'].move(-camera_x, 0)
        if draw_rect.right >= 0 and draw_rect.left <= WIDTH:
            # 弹起动画（和 bumped_blocks 同步）
            bid = id(hb['rect'])
            offset_y = 0
            if bid in bumped_blocks:
                b_info = bumped_blocks[bid]
                # 上半段向上弹，下半段回位
                half = b_info['max_t'] // 2
                if b_info['t'] < half:
                    offset_y = -int((b_info['t'] / half) * 4)  # 向上弹最多 4px
                else:
                    offset_y = -int(((b_info['max_t'] - b_info['t']) / half) * 4)
                b_info['t'] += 1
                if b_info['t'] >= b_info['max_t']:
                    bumped_blocks.pop(bid, None)
            screen.blit(_empty_img, draw_rect.move(0, offset_y))

    # 绘制世界中的金币
    for coin in coins_in_world[:]:
        if not coin.get('collecting', False):
            draw_rect = coin['rect'].move(-camera_x, 0)
            if draw_rect.right >= 0 and draw_rect.left <= WIDTH:
                if coin_frames_world:
                    frm = coin['frame'] % len(coin_frames_world)
                    screen.blit(coin_frames_world[frm], draw_rect)
                    coin['timer'] += 1
                    if coin['timer'] >= 8:
                        coin['timer'] = 0
                        coin['frame'] = (coin['frame'] + 1) % len(coin_frames_world)

    # 绘制正在播放收集动画的金币
    for coin in coins_in_world[:]:
        if coin.get('collecting', False):
            # 收集动画：直接上升→下落（无等待）
            if coin.get('rise_frames', 0) > 0:
                coin['rect'].y -= 10  # 提高上升速度
                coin['rise_frames'] -= 1
            else:
                coin['y_v'] = coin.get('y_v', 0) + GRAVITY
                coin['rect'].y += coin['y_v']
            # 绘制动画中的金币
            draw_rect = coin['rect'].move(-camera_x, 0)
            if coin_frames_world:
                frm = coin['frame'] % len(coin_frames_world)
                screen.blit(coin_frames_world[frm], draw_rect)
            # 动画结束，移除金币
            if coin['rect'].top > HIGH:
                coins_in_world.remove(coin)

    # 检测马里奥与金币碰撞
    for coin in coins_in_world[:]:
        if not coin.get('collecting', False) and mario.rect.colliderect(coin['rect']):
            # 收集金币：计数+音效+开始动画（不再立即加分，通关时统一换算）
            coins += 1
            try:
                if gold_sound:
                    gold_sound.play()
            except Exception:
                pass
            # 开始收集动画
            coin['collecting'] = True
            coin['rise_frames'] = int(FPS * 0.25)  # 上升 0.25 秒，抬得更高
            coin['y_v'] = 0
            
            # 100金币加一条命
            if coins >= 100:
                coins -= 100
                lives += 1

    # 绘制正在从问号砖块中冒出的无敌星
    for star in emerging_stars[:]:
        draw_rect = star['rect'].move(-camera_x, 0)
        if draw_rect.right >= 0 and draw_rect.left <= WIDTH:
            frm = star['frame'] % len(star_frames)
            screen.blit(star_frames[frm], draw_rect)
            star['frame'] = (star['frame'] + 1) % len(star_frames)

    # 更新世界中的无敌星移动并绘制
    for star in stars_in_world[:]:
        # 应用重力
        star['y_v'] = star.get('y_v', 0) + GRAVITY
        star['rect'].y += star['y_v']
        # 垂直方向与地面/平台碰撞处理（让星星落在地面或平台上）
        for obs in blocks + obstacles:
            if star['rect'].colliderect(obs):
                if star['y_v'] > 0:
                    star['rect'].bottom = obs.top
                    star['y_v'] = 0
                elif star['y_v'] < 0:
                    star['rect'].top = obs.bottom
                    star['y_v'] = 0

        # 水平移动及与障碍物反弹
        old_x = star['rect'].x
        star['rect'].x += star.get('x_v', 3)
        if any(star['rect'].colliderect(obs) for obs in obstacles):
            star['rect'].x = old_x
            star['x_v'] = -star.get('x_v', 3)

        draw_rect = star['rect'].move(-camera_x, 0)
        if draw_rect.right >= 0 and draw_rect.left <= WIDTH:
            frm = star['frame'] % len(star_frames)
            screen.blit(star_frames[frm], draw_rect)
            star['timer'] += 1
            if star['timer'] >= 6:
                star['timer'] = 0
                star['frame'] = (star['frame'] + 1) % len(star_frames)

    # 绘制 Super Mushroom
    if super_mushroom_img:
        for msh in mushrooms_in_world:
            draw_rect = msh['rect'].move(-camera_x, 0)
            if draw_rect.right >= 0 and draw_rect.left <= WIDTH:
                screen.blit(super_mushroom_img, draw_rect)

    # 检测马里奥与无敌星碰撞
    for star in stars_in_world[:]:
        if mario.rect.colliderect(star['rect']):
            stars_in_world.remove(star)
            # 进入无敌状态
            invincible_timer = INVINCIBILITY_DURATION
            score += 1000
            # 保存当前BGM，切换到无敌BGM
            original_bgm = pygame.mixer.music.get_busy()
            pygame.mixer.music.stop()
            if invincibility_music:
                invincibility_music.play(-1)  # 循环播放

    # 检测马里奥与 Super Mushroom 碰撞（吃了变大）
    for msh in mushrooms_in_world[:]:
        if mario.rect.colliderect(msh['rect']):
            # 上方被挡则吃不到（蘑菇留在原地）
            env = blocks + obstacles + pipes
            new_top = mario.rect.bottom - mario.big_h
            probe = pygame.Rect(mario.rect.left, new_top, mario.rect.width, mario.big_h - mario.rect.height)
            if probe_is_blocked(probe, env):
                continue
            # 移除蘑菇并触发 grow morph
            mushrooms_in_world.remove(msh)
            if mario.morph_state == 'none':
                mario.start_grow()  # 内部已播放 power_up_sound (SMB1 Power-Up)
                score += 1000

    # 检测马里奥与 Fire Flower 碰撞（吃了变 Fire Mario）
    for ff in fire_flowers_in_world[:]:
        if mario.rect.colliderect(ff['rect']):
            fire_flowers_in_world.remove(ff)
            if mario.morph_state == 'none':
                if not mario.is_big:
                    # 小马里奥吃 Fire Flower：先 grow
                    mario.start_grow()
                # 变成 Fire Mario
                mario.fire_mode = True
                mario.update_sprite()
                try:
                    if power_up_sound: power_up_sound.play()
                except Exception: pass
                score += 1000

    # 无敌状态计时（含1秒宽限期：滤镜消失但仍无敌）
    if invincible_timer > 0:
        invincible_timer -= 1
        # 最后3秒开始闪烁滤镜淡出
        if invincible_timer <= INVINCIBILITY_GRACE * 3:
            # 进入宽限期前，开始闪烁效果
            pass
        if invincible_timer <= 0:
            invincible_timer = 0
            # 无敌滤镜结束，开始宽限期
            invincible_grace_timer = INVINCIBILITY_GRACE
            if invincibility_music:
                invincibility_music.stop()
            try:
                if waiting_for_invincibility:
                    pass
                else:
                    pygame.mixer.music.play(-1)
            except Exception:
                pass
    elif invincible_grace_timer > 0:
        invincible_grace_timer -= 1
        if invincible_grace_timer <= 0:
            invincible_grace_timer = 0

    # 处理时间警告（剩余时间<100时切换到加速版BGM）
    if not mario.dead and pass_phase == 0:
        handle_timer_warning()

    screen.blit(get_fortress_img(), (fortress_rect.x - camera_x, fortress_rect.y))

    # 绘制通关城堡
    if castle_spawned:
        screen.blit(get_castle_img(), (castle_rect.x - camera_x, castle_rect.y))
        # 检测马里奥进入城堡触发通关
        if not mario.dead and pass_phase == 0 and mario.rect.colliderect(castle_rect):
            pass_phase = 1
            pass_timer = 0
            pass_mario_hidden = False
            # 清除无敌状态
            if invincible_timer > 0 or invincible_grace_timer > 0:
                invincible_timer = 0
                invincible_grace_timer = 0
                if invincibility_music:
                    invincibility_music.stop()
            pygame.mixer.music.stop()
            if pass_sound:
                pass_channel = pass_sound.play()

    # 蘑菇怪踩踏标记（防止贴贴时重复检测导致死亡）
    stomacked_goomba = False
    for goomba in goombas[:]:
        goomba.update(blocks + obstacles)
        if goomba.dead and goomba.dead_timer >= GOOMBA_VANISH_FRAMES:
            goombas.remove(goomba)
            continue
        # 通关走向终点时不触发死亡，只处理踩踏
        if not mario.dead and not stomacked_goomba and not goomba.dead and not goomba.shell_killed and mario.rect.colliderect(goomba.rect):
            if invincible_timer > 0 or invincible_grace_timer > 0 or pass_phase > 0:
                # 无敌状态或通关中：蘑菇怪播放被乌龟撞的动画（shell kill）
                direction = 1 if mario.rect.centerx < goomba.rect.centerx else -1
                goomba.die(shell=True, direction=direction)
                if goomba_death_sound:
                    goomba_death_sound.play()
                score += 100
                stomacked_goomba = True
                # 无敌/通关时仅击杀敌人，不再把角色 Y 轴抬起
            else:
                goomba_mid_y = goomba.rect.top + goomba.rect.height // 2
                if mario.y_v > 0 and mario.rect.bottom <= goomba_mid_y:
                    pts = award_stomp_score(mario)
                    goomba.die()
                    if goomba_death_sound:
                        goomba_death_sound.play()
                    mario.y_v = JUMP_POWER / 2
                    stomacked_goomba = True
                    mario.rect.bottom = goomba.rect.top - 1  # 立即脱离碰撞区
                elif not mario.dead:
                    if mario.is_big:
                        mario.shrink()
                        invincible_grace_timer = 70  # morph 期间无敌防二次碰撞
                        mario.rect.bottom = goomba.rect.top - 1  # 移出碰撞区
                        mario.rect.y -= 6
                    else:
                        mario.rect.y -= 10
                        start_death(mario)
        goomba.draw(screen, camera_x)

    # 乌龟踩踏标记（防止贴贴时重复检测导致死亡）
    stomacked_koopa = False
    for koopa in koopas[:]:
        koopa.update(blocks + obstacles, goombas, koopas)
        if koopa.dead:
            koopas.remove(koopa)
            continue
        # 通关走向终点时不触发死亡，只处理踩踏
        if not mario.dead and not stomacked_koopa and mario.rect.colliderect(koopa.rect):
            # 判断是否从上方踩踏（马里奥底部接近乌龟顶部且下落中）
            is_stomp_from_above = mario.y_v > 0 and mario.rect.bottom - koopa.rect.top < 12
            
            if invincible_timer > 0 or invincible_grace_timer > 0 or pass_phase > 0:
                # 无敌状态或通关中：直接击杀乌龟
                koopa.die()
                if goomba_death_sound:
                    goomba_death_sound.play()
                score += 100
                stomacked_koopa = True
                # 无敌/通关时仅击杀敌人，不再把角色 Y 轴抬起
                
            elif koopa.state == "walk":
                # 行走中的乌龟
                if is_stomp_from_above:
                    pts = award_stomp_score(mario)
                    koopa.stomp()
                    if goomba_death_sound:
                        goomba_death_sound.play()
                    mario.y_v = JUMP_POWER / 2
                    stomacked_koopa = True
                    mario.rect.bottom = koopa.rect.top - 1
                else:
                    # 侧面撞击 → 死亡 / 大马里奥缩身
                    if mario.is_big:
                        mario.shrink()
                        invincible_grace_timer = 70
                        mario.rect.bottom = koopa.rect.top - 1
                        mario.rect.y -= 6
                    else:
                        mario.rect.y -= 10
                        start_death(mario)
                    
            elif koopa.state == "shell_static":
                # 静止壳：马里奥怎么碰都不会受伤
                direction = 1 if mario.rect.centerx < koopa.rect.centerx else -1
                if is_stomp_from_above:
                    koopa.kick(direction)
                    mario.y_v = JUMP_POWER / 2
                else:
                    koopa.kick(direction)
                    
            elif koopa.state == "shell_slide":
                # 滑行中的壳：踩上面弹开+音效，侧面撞击才死
                if is_stomp_from_above:
                    # 从上方踩：弹开，壳不停
                    mario.y_v = JUMP_POWER / 2
                    if goomba_death_sound:
                        goomba_death_sound.play()
                    stomacked_koopa = True
                    mario.rect.bottom = koopa.rect.top - 1
                else:
                    # 侧面撞击移动中的壳 → 死亡 / 大马里奥缩身
                    if mario.is_big:
                        mario.shrink()
                        invincible_grace_timer = 70
                        mario.rect.bottom = koopa.rect.top - 1
                        mario.rect.y -= 6
                    else:
                        mario.rect.y -= 10
                        start_death(mario)
        koopa.update_sprite()
        koopa.draw(screen, camera_x)

    # ========== Fire Flower 渲染 ==========
    for ff in fire_flowers_in_world:
        ff['rect'].y -= 0  # 占位（rise_frames 已处理上移）
        if ff.get('rise_frames', 0) <= 0:
            pass  # 静止在砖块上方
        if fire_flower_img:
            screen.blit(fire_flower_img, (ff['rect'].x - camera_x, ff['rect'].y))

    # ========== 火球物理 + 碰撞 + 渲染 ==========
    _env_blocks = blocks + obstacles + pipes
    for fb in fireballs[:]:
        if not fb['alive']:
            fireballs.remove(fb)
            continue
        fb['frame_timer'] += 1
        # 重力
        fb['y_v'] = min(fb['y_v'] + GRAVITY * 0.6, 12)
        # 水平移动
        fb['rect'].x += fb['x_v']
        # 水平碰墙 → 消失
        for blk in _env_blocks:
            if fb['rect'].colliderect(blk):
                fb['alive'] = False
                break
        if not fb['alive']:
            fireballs.remove(fb)
            continue
        # 垂直移动 + 落地反弹
        fb['rect'].y += fb['y_v']
        for blk in _env_blocks:
            if fb['rect'].colliderect(blk):
                if fb['y_v'] > 0 and fb['rect'].bottom - fb['y_v'] <= blk.top + 1:
                    # 落地反弹
                    fb['rect'].bottom = blk.top
                    fb['y_v'] = -max(3, abs(fb['y_v']) * 0.7)
                    fb['bounces'] += 1
                    if fb['bounces'] >= 3:
                        fb['alive'] = False
                elif fb['y_v'] < 0:
                    fb['rect'].top = blk.bottom
                    fb['alive'] = False
                break
        if not fb['alive']:
            fireballs.remove(fb)
            continue
        # 掉出屏幕
        if fb['rect'].top > HIGH + 50 or fb['rect'].left < -50 or fb['rect'].right > WIDTH + 50:
            fb['alive'] = False
            fireballs.remove(fb)
            continue
        # 火球杀 Goomba
        for goomba in goombas[:]:
            if not goomba.dead and not goomba.shell_killed and fb['rect'].colliderect(goomba.rect):
                goomba.dead = True
                goomba.death_timer = 0
                fb['alive'] = False
                score += 100
                try:
                    if goomba_death_sound: goomba_death_sound.play()
                except Exception: pass
                break
        if not fb['alive']:
            fireballs.remove(fb)
            continue
        # 火球杀 Koopa（shell_slide 状态被击中 → 弹走，walk 状态 → 变 shell）
        for koopa in koopas[:]:
            if fb['rect'].colliderect(koopa.rect):
                if koopa.state == "walk":
                    koopa.state = "shell_static"
                    koopa.x_v = 0
                    score += 100
                elif koopa.state == "shell_static":
                    # 踢飞
                    koopa.state = "shell_slide"
                    koopa.x_v = 7 if koopa.rect.centerx < fb['rect'].centerx else -7
                    score += 100
                fb['alive'] = False
                try:
                    if goomba_death_sound: goomba_death_sound.play()
                except Exception: pass
                break
        if not fb['alive']:
            fireballs.remove(fb)
            continue
        # 渲染火球（带动画帧切换）
        _f_idx = fb['frame_timer'] % max(1, len(fireball_frames))
        _fb_img = fireball_frames[_f_idx] if fireball_frames else fireball_img
        screen.blit(_fb_img, (fb['rect'].x - camera_x, fb['rect'].y))

    if mario.dead:
        if getattr(mario, 'is_pit_death', False):
            # 掉坑死亡：上升→暂停→下落
            if mario.death_rise_frames > 0:
                rise_speed = getattr(mario, 'death_rise_speed', PIT_DEATH_RISE_SPEED)
                mario.rect.y -= rise_speed
                mario.death_rise_frames -= 1
            elif mario.death_pause > 0:
                mario.death_pause -= 1
            else:
                mario.y_v += GRAVITY
                mario.rect.y += mario.y_v
        else:
            # 普通死亡：原地等待→上升→下落
            if mario.death_pause > 0:
                mario.death_pause -= 1
            elif mario.death_rise_frames > 0:
                rise_speed = getattr(mario, 'death_rise_speed', DEATH_RISE_SPEED)
                mario.rect.y -= rise_speed
                mario.death_rise_frames -= 1
            else:
                mario.y_v += GRAVITY
                mario.rect.y += mario.y_v
        if mario.rect.top > HIGH and death_screen_phase == 0:
            if not death_wait_for_music or (death_channel and not death_channel.get_busy()):
                death_screen_phase = 1
                death_screen_timer = 0
                death_wait_for_music = False
                death_channel = None

    # 通关动画
    if pass_phase > 0:
        # 阶段1：马里奥走向城堡中间
        if pass_phase == 1:
            castle_center_x = castle_rect.x + castle_rect.width // 2
            if mario.rect.centerx < castle_center_x:
                mario.rect.x += 2
                mario.facing = "right"
                mario.x_v = 2  # 设置x_v使update_sprite切换到run动画
            else:
                mario.x_v = 0
                pass_phase = 2
                pass_mario_hidden = True
                pass_timer = 0
            mario.update_sprite()
            mario.draw(screen, camera_x)
        # 阶段2：马里奥隐藏，播放音效并立即开始时间转分数
        elif pass_phase == 2:
            pass_phase = 3
            pass_timer = 0
            # 保存剩余时间用于转换
            time_to_convert = float(time_left)
            time_left = 0  # 防止触发死亡
            # 动态计算每帧转换步长，确保胜利音乐播完时转换完成
            if PASS_SOUND_FRAMES > 0 and time_to_convert > 0:
                time_convert_step = time_to_convert / PASS_SOUND_FRAMES
            else:
                time_convert_step = 0
            # 仍然绘制城堡
            screen.blit(get_castle_img(), (castle_rect.x - camera_x, castle_rect.y))
        # 阶段3：时间转分数动画
        elif pass_phase == 3:
            pass_timer += 1
            # 每帧按动态步长减少时间，增加分数
            if time_to_convert > 0 and time_convert_step > 0:
                step = min(time_convert_step, time_to_convert)
                time_to_convert -= step
                score += int(50 * step)
                time_left = int(time_to_convert)
            else:
                # 动画结束，等待音效播放完成后再进入结算
                if not pass_channel or not pass_channel.get_busy():
                    # 金币换算为积分（每枚金币200分）
                    score += coins * 200
                    # 保存最高分
                    if score > high_score:
                        high_score = score
                        save_high_score(high_score)
                    # 保存当前关卡的完整地形到会话缓存
                    save_level_to_cache()
                    death_screen_phase = 1
                    death_screen_timer = 0
                    pass_phase = 0
                    pass_settlement = True
                    is_final_world = advance_world()
                    coins = 0
            # 绘制状态栏（通关也保持地下/地表背景一致）
            draw_status_bar(screen, bg_color=_status_bg, top_padding=STATUS_BAR_TOP_PADDING)
            screen.blit(get_castle_img(), (castle_rect.x - camera_x, castle_rect.y))
        pygame.display.update()
        tick_and_update_fps()
        continue

    # 更新并绘制砖块破碎粒子
    for piece in bricks_broken[:]:
        piece.update()
        if piece.life <= 0:
            bricks_broken.remove(piece)
    for piece in bricks_broken:
        piece.draw(screen, camera_x)

    mario.draw(screen, camera_x)

    # 管道进入动画期间：补绘管道（画在马里奥上面，视觉遮挡下沉/冒头）
    if pipe_enter_state != 'none':
        for ob in obstacles:
            if ob in pipes:
                draw_rect = ob.move(-camera_x, 0)
                if draw_rect.right >= 0 and draw_rect.left <= WIDTH:
                    screen.blit(pipe_img, draw_rect)

    # 触控模式覆盖层：只在游戏中画（标题页不画）
    if TOUCH_MODE and game_state in ('playing', 'game_over', 'intro'):
        _draw_touch_overlay(screen, camera_x, mario)

    # ======== God Mode Debug 覆盖层 ========
    if GOD_MODE and game_state in ('playing', 'intro'):
        _debug_boxes = globals().get('_debug_show_boxes', False)
        _debug_info = globals().get('_debug_info', False)
        if _debug_boxes:
            # Mario
            _mx, _my = mario.rect.x - camera_x, mario.rect.y
            pygame.draw.rect(screen, (0, 255, 0), (_mx, _my, mario.rect.width, mario.rect.height), 1)
            # 砖块/障碍物
            for _b in blocks + obstacles:
                _rx = _b.x - camera_x
                if _rx + _b.width < 0 or _rx > WIDTH: continue
                pygame.draw.rect(screen, (100, 200, 255), (_rx, _b.y, _b.width, _b.height), 1)
            # 管道
            for _p in pipes:
                _rx = _p.x - camera_x
                if _rx + _p.width < 0 or _rx > WIDTH: continue
                pygame.draw.rect(screen, (100, 255, 100), (_rx, _p.y, _p.width, _p.height), 1)
            # 隐藏砖块（content 标出来）
            for _hb in hidden_blocks:
                _rx = _hb['rect'].x - camera_x
                if _rx + _hb['rect'].width < 0 or _rx > WIDTH: continue
                _c = (255, 200, 0) if _hb.get('content') == '1up' else (255, 100, 100)
                pygame.draw.rect(screen, _c, (_rx, _hb['rect'].y, _hb['rect'].width, _hb['rect'].height), 2)
            # 敌人
            for _g in goombas:
                _rx = _g.rect.x - camera_x
                pygame.draw.rect(screen, (255, 100, 100), (_rx, _g.rect.y, _g.rect.width, _g.rect.height), 1)
            for _k in koopas:
                _rx = _k.rect.x - camera_x
                pygame.draw.rect(screen, (100, 255, 100), (_rx, _k.rect.y, _k.rect.width, _k.rect.height), 1)
        if _debug_info:
            try:
                try:
                    _df = pygame.font.Font(STATUS_FONT_PATH, 16)
                except Exception:
                    _df = pygame.font.SysFont('arial', 16, bold=True)
                _lines = [
                    f"GOD MODE {'(touch)' if TOUCH_MODE else ''}",
                    f"  pos: ({mario.rect.x}, {mario.rect.y})",
                    f"  vx/vy: ({mario.x_v:.1f}, {mario.y_v:.1f})",
                    f"  on_ground: {mario.on_ground}",
                    f"  is_big: {mario.is_big}  fire: {mario.fire_mode}",
                    f"  invincible: {invincible_timer}",
                    f"  world: {WORLD_STR}  width: {world_width}",
                    f"  lives: {lives}  coins: {coins}  score: {score}",
                    f"  underground: {is_underground}",
                ]
                for _i, _line in enumerate(_lines):
                    _surf = _df.render(_line, True, (255, 255, 0))
                    screen.blit(_surf, (10, 40 + _i * 18))
            except Exception as _e:
                print(f"[GOD] debug info error: {_e}")

    tick_and_update_fps()
    pygame.display.update()

pygame.quit()