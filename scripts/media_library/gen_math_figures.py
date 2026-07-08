# -*- coding: utf-8 -*-
"""批量生成黑板风教学插图（自制，版权干净），供 ingest.py 入库。

配色与 M5 黑板前端一致（板面 #232a20 / 粉笔白 #e8e2d6 / 暖橙 #de5e39 /
绿 #5a8a72 / 粉笔黄 #ecc06a），插到黑板上风格统一不刺眼。

产物落 scripts/media_library/generated/：
  - *.png / *.gif         图片本体
  - manifest.json         逐张元数据（ingest.py 的输入）

运行: D:\\anaconda3\\envs\\edu\\python.exe scripts\\media_library\\gen_math_figures.py
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

BOARD = "#232a20"
CHALK = "#e8e2d6"
ORANGE = "#de5e39"
GREEN = "#5a8a72"
YELLOW = "#ecc06a"
DIM = "#9a937f"

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated")


def _new_ax(figsize=(8, 5)):
    fig, ax = plt.subplots(figsize=figsize, facecolor=BOARD)
    ax.set_facecolor(BOARD)
    for spine in ax.spines.values():
        spine.set_color(DIM)
    ax.tick_params(colors=DIM, labelsize=9)
    return fig, ax


def _save(fig, name):
    path = os.path.join(OUT_DIR, name)
    fig.savefig(path, dpi=110, facecolor=BOARD, bbox_inches="tight")
    plt.close(fig)
    print(f"  生成 {name}")


# ---------------- 数学 ----------------

def fig_tangent_secant():
    fig, ax = _new_ax()
    x = np.linspace(-0.6, 2.6, 200)
    ax.plot(x, x ** 2, color=CHALK, lw=2.2, label="y = x²")
    # P(1,1) 处切线 y=2x-1
    ax.plot(x, 2 * x - 1, color=ORANGE, lw=2, label="切线（斜率 = 2）")
    # 割线过 P(1,1)、Q(2,4)
    ax.plot(x, 3 * x - 2, color=GREEN, lw=1.6, ls="--", label="割线 PQ（斜率 = 3）")
    ax.plot([1], [1], "o", color=YELLOW, ms=8, zorder=5)
    ax.plot([2], [4], "o", color=GREEN, ms=7, zorder=5)
    ax.annotate("P(1, 1)", (1, 1), xytext=(1.12, 0.55), color=YELLOW, fontsize=12)
    ax.annotate("Q(2, 4)", (2, 4), xytext=(2.08, 3.7), color=GREEN, fontsize=12)
    ax.annotate("Q 沿曲线滑向 P，割线逼近切线", (0.0, 5.0), color=CHALK, fontsize=12)
    ax.set_ylim(-1.6, 6.4)
    ax.legend(loc="lower right", facecolor=BOARD, edgecolor=DIM, labelcolor=CHALK)
    ax.set_title("导数的几何意义：割线逼近切线", color=CHALK, fontsize=14)
    _save(fig, "math_tangent_secant.png")


def fig_extremum():
    fig, ax = _new_ax()
    x = np.linspace(-2.4, 2.4, 300)
    y = x ** 3 - 3 * x
    ax.plot(x, y, color=CHALK, lw=2.2, label="y = x³ − 3x")
    for x0, kind, col in [(-1, "极大值点", ORANGE), (1, "极小值点", GREEN)]:
        y0 = x0 ** 3 - 3 * x0
        ax.plot([x0 - 0.7, x0 + 0.7], [y0, y0], color=col, lw=2)
        ax.plot([x0], [y0], "o", color=YELLOW, ms=8, zorder=5)
        ax.annotate(f"{kind}\n切线水平 f′={0}", (x0, y0),
                    xytext=(x0 - 0.55, y0 + (0.9 if col == ORANGE else -1.8)),
                    color=col, fontsize=11)
    ax.set_ylim(-4.5, 4.5)
    ax.legend(loc="lower right", facecolor=BOARD, edgecolor=DIM, labelcolor=CHALK)
    ax.set_title("极值点处导数为零（切线水平）", color=CHALK, fontsize=14)
    _save(fig, "math_extremum.png")


def fig_integral_area():
    fig, ax = _new_ax()
    x = np.linspace(-0.4, 1.6, 200)
    ax.plot(x, x ** 2, color=CHALK, lw=2.2, label="y = x²")
    xs = np.linspace(0, 1, 100)
    ax.fill_between(xs, xs ** 2, color=GREEN, alpha=0.45, label="曲边梯形面积 = 1/3")
    # 微元示意
    ax.bar(0.62, 0.62 ** 2, width=0.07, align="edge", color=ORANGE, alpha=0.85)
    ax.annotate("微元 f(x)·dx", (0.66, 0.42), xytext=(0.86, 0.78), color=ORANGE,
                fontsize=12, arrowprops=dict(arrowstyle="->", color=ORANGE))
    ax.axvline(0, color=DIM, lw=0.8)
    ax.axvline(1, color=DIM, lw=0.8, ls=":")
    ax.set_ylim(-0.25, 2.2)
    ax.legend(loc="upper left", facecolor=BOARD, edgecolor=DIM, labelcolor=CHALK)
    ax.set_title("定积分的几何意义：曲线下的面积", color=CHALK, fontsize=14)
    _save(fig, "math_integral_area.png")


def fig_normal_curves():
    fig, ax = _new_ax()
    x = np.linspace(-6, 6, 400)
    for mu, sigma, col, label in [(0, 1, ORANGE, "μ=0, σ=1（瘦高）"),
                                  (0, 2, GREEN, "μ=0, σ=2（矮胖）"),
                                  (2, 1, YELLOW, "μ=2, σ=1（右移）")]:
        y = np.exp(-(x - mu) ** 2 / (2 * sigma ** 2)) / (sigma * np.sqrt(2 * np.pi))
        ax.plot(x, y, color=col, lw=2.2, label=label)
    ax.axvline(0, color=DIM, lw=0.8, ls=":")
    ax.legend(facecolor=BOARD, edgecolor=DIM, labelcolor=CHALK)
    ax.set_title("正态分布：μ 决定中心，σ 决定胖瘦", color=CHALK, fontsize=14)
    _save(fig, "math_normal_curves.png")


def fig_exp_log():
    fig, ax = _new_ax(figsize=(6.6, 6))
    x1 = np.linspace(-2.2, 2.2, 200)
    ax.plot(x1, np.exp(x1), color=ORANGE, lw=2.2, label="y = $e^x$")
    x2 = np.linspace(0.08, 8, 300)
    ax.plot(x2, np.log(x2), color=GREEN, lw=2.2, label="y = ln x")
    x3 = np.linspace(-2.2, 8, 50)
    ax.plot(x3, x3, color=DIM, lw=1.2, ls="--", label="y = x（对称轴）")
    ax.set_xlim(-2.5, 8)
    ax.set_ylim(-2.5, 8)
    ax.set_aspect("equal")
    ax.axhline(0, color=DIM, lw=0.8)
    ax.axvline(0, color=DIM, lw=0.8)
    ax.legend(loc="upper left", facecolor=BOARD, edgecolor=DIM, labelcolor=CHALK)
    ax.set_title("指数与对数互为反函数（关于 y=x 对称）", color=CHALK, fontsize=13)
    _save(fig, "math_exp_log.png")


def fig_sin_cos():
    fig, ax = _new_ax(figsize=(9, 4.2))
    x = np.linspace(-2 * np.pi, 2 * np.pi, 400)
    ax.plot(x, np.sin(x), color=ORANGE, lw=2.2, label="y = sin x")
    ax.plot(x, np.cos(x), color=GREEN, lw=2.2, label="y = cos x")
    ax.axhline(0, color=DIM, lw=0.8)
    ax.set_xticks(np.pi * np.array([-2, -1, 0, 1, 2]))
    ax.set_xticklabels(["−2π", "−π", "0", "π", "2π"])
    ax.annotate("相位差 π/2", (np.pi / 4, 1.06), color=YELLOW, fontsize=12)
    ax.set_ylim(-1.45, 1.45)
    ax.legend(loc="lower left", facecolor=BOARD, edgecolor=DIM, labelcolor=CHALK)
    ax.set_title("正弦与余弦：周期 2π，相差 π/2", color=CHALK, fontsize=14)
    _save(fig, "math_sin_cos.png")


def fig_unit_circle():
    fig, ax = _new_ax(figsize=(6.4, 6))
    t = np.linspace(0, 2 * np.pi, 200)
    ax.plot(np.cos(t), np.sin(t), color=CHALK, lw=2)
    th = np.pi / 4 * 1.4  # 63°
    cx, sy = np.cos(th), np.sin(th)
    ax.plot([0, cx], [0, sy], color=YELLOW, lw=2.2)
    ax.plot([cx, cx], [0, sy], color=ORANGE, lw=2.2, label="sin θ（纵坐标）")
    ax.plot([0, cx], [0, 0], color=GREEN, lw=2.6, label="cos θ（横坐标）")
    ax.plot([cx], [sy], "o", color=YELLOW, ms=8)
    arc = np.linspace(0, th, 50)
    ax.plot(0.25 * np.cos(arc), 0.25 * np.sin(arc), color=DIM, lw=1.2)
    ax.annotate("θ", (0.3, 0.13), color=CHALK, fontsize=14)
    ax.annotate("P(cos θ, sin θ)", (cx, sy), xytext=(cx + 0.07, sy + 0.05),
                color=YELLOW, fontsize=12)
    ax.axhline(0, color=DIM, lw=0.8)
    ax.axvline(0, color=DIM, lw=0.8)
    ax.set_xlim(-1.35, 1.55)
    ax.set_ylim(-1.3, 1.4)
    ax.set_aspect("equal")
    ax.legend(loc="lower left", facecolor=BOARD, edgecolor=DIM, labelcolor=CHALK)
    ax.set_title("单位圆定义三角函数", color=CHALK, fontsize=14)
    _save(fig, "math_unit_circle.png")


def fig_vector_add():
    fig, ax = _new_ax(figsize=(7, 5.4))
    a = np.array([3, 1])
    b = np.array([1, 2.4])
    kw = dict(angles="xy", scale_units="xy", scale=1, width=0.012)
    ax.quiver(0, 0, a[0], a[1], color=ORANGE, **kw)
    ax.quiver(0, 0, b[0], b[1], color=GREEN, **kw)
    ax.quiver(0, 0, a[0] + b[0], a[1] + b[1], color=YELLOW, **kw)
    ax.plot([a[0], a[0] + b[0]], [a[1], a[1] + b[1]], color=GREEN, lw=1.3, ls="--")
    ax.plot([b[0], a[0] + b[0]], [b[1], a[1] + b[1]], color=ORANGE, lw=1.3, ls="--")
    ax.annotate("a", (1.6, 0.28), color=ORANGE, fontsize=15, style="italic")
    ax.annotate("b", (0.28, 1.3), color=GREEN, fontsize=15, style="italic")
    ax.annotate("a + b", (2.0, 2.0), color=YELLOW, fontsize=15, style="italic")
    ax.set_xlim(-0.5, 5)
    ax.set_ylim(-0.5, 4.2)
    ax.set_aspect("equal")
    ax.set_title("向量加法：平行四边形法则", color=CHALK, fontsize=14)
    _save(fig, "math_vector_add.png")


# ---------------- 物理 ----------------

def gif_wave():
    fig, ax = _new_ax(figsize=(8, 3.8))
    x = np.linspace(0, 4, 300)
    lam, v = 2.0, 1.0
    line, = ax.plot([], [], color=CHALK, lw=2.2)
    dot, = ax.plot([], [], "o", color=ORANGE, ms=10, zorder=5)
    ax.axhline(0, color=DIM, lw=0.8)
    ax.annotate("波形向右传播 →", (0.15, 1.18), color=YELLOW, fontsize=12)
    ax.annotate("质点只上下振动（看橙点）", (0.15, -1.38), color=ORANGE, fontsize=12)
    ax.set_xlim(0, 4)
    ax.set_ylim(-1.6, 1.6)
    ax.set_title("横波的传播", color=CHALK, fontsize=14)
    x_dot = 2.0

    def update(frame):
        t = frame / 20.0
        y = np.sin(2 * np.pi * (x - v * t) / lam)
        line.set_data(x, y)
        dot.set_data([x_dot], [np.sin(2 * np.pi * (x_dot - v * t) / lam)])
        return line, dot

    anim = FuncAnimation(fig, update, frames=40, blit=True)
    path = os.path.join(OUT_DIR, "physics_wave.gif")
    anim.save(path, writer=PillowWriter(fps=20), savefig_kwargs={"facecolor": BOARD})
    plt.close(fig)
    print("  生成 physics_wave.gif")


def gif_shm():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 3.8), facecolor=BOARD,
                                   gridspec_kw={"width_ratios": [1, 2.2]})
    for ax in (ax1, ax2):
        ax.set_facecolor(BOARD)
        for spine in ax.spines.values():
            spine.set_color(DIM)
        ax.tick_params(colors=DIM, labelsize=8)
    # 左：振子在竖直方向振动；右：位移-时间曲线同步展开
    ax1.set_xlim(-1, 1)
    ax1.set_ylim(-1.6, 1.6)
    ax1.set_xticks([])
    ax1.axhline(0, color=DIM, lw=0.8, ls=":")
    ax1.set_title("振子", color=CHALK, fontsize=12)
    ball, = ax1.plot([], [], "o", color=ORANGE, ms=16)
    spring, = ax1.plot([], [], color=DIM, lw=1.4)
    ax2.set_xlim(0, 4)
    ax2.set_ylim(-1.6, 1.6)
    ax2.axhline(0, color=DIM, lw=0.8)
    ax2.set_title("位移 – 时间图像（正弦曲线）", color=CHALK, fontsize=12)
    curve, = ax2.plot([], [], color=CHALK, lw=2)
    head, = ax2.plot([], [], "o", color=ORANGE, ms=8)
    T = 2.0

    def update(frame):
        t = frame / 20.0
        y0 = np.cos(2 * np.pi * t / T)
        ball.set_data([0], [y0])
        spring.set_data([0, 0], [1.6, y0])
        ts = np.linspace(0, t, max(int(t * 60), 2))
        curve.set_data(ts, np.cos(2 * np.pi * ts / T))
        head.set_data([t], [y0])
        return ball, spring, curve, head

    anim = FuncAnimation(fig, update, frames=80, blit=True)
    path = os.path.join(OUT_DIR, "physics_shm.gif")
    anim.save(path, writer=PillowWriter(fps=20), savefig_kwargs={"facecolor": BOARD})
    plt.close(fig)
    print("  生成 physics_shm.gif")


def fig_projectile():
    fig, ax = _new_ax(figsize=(8, 4.6))
    v0, g, h0 = 4.0, 9.8, 4.0
    t_land = np.sqrt(2 * h0 / g)
    t = np.linspace(0, t_land, 100)
    ax.plot(v0 * t, h0 - 0.5 * g * t ** 2, color=CHALK, lw=2.2, label="轨迹（抛物线）")
    for tf in np.linspace(0.15, t_land * 0.92, 4):
        px, py = v0 * tf, h0 - 0.5 * g * tf ** 2
        ax.quiver(px, py, 0.7, 0, color=GREEN, angles="xy", scale_units="xy", scale=1, width=0.008)
        ax.quiver(px, py, 0, -g * tf * 0.18, color=ORANGE, angles="xy", scale_units="xy", scale=1, width=0.008)
        ax.plot([px], [py], "o", color=YELLOW, ms=5)
    ax.annotate("水平：匀速（绿）", (2.6, 3.7), color=GREEN, fontsize=12)
    ax.annotate("竖直：自由落体（橙）", (2.6, 3.2), color=ORANGE, fontsize=12)
    ax.axhline(0, color=DIM, lw=1)
    ax.set_ylim(-0.4, 4.6)
    ax.legend(loc="lower left", facecolor=BOARD, edgecolor=DIM, labelcolor=CHALK)
    ax.set_title("平抛运动 = 水平匀速 + 竖直自由落体", color=CHALK, fontsize=14)
    _save(fig, "physics_projectile.png")


def fig_incline_forces():
    fig, ax = _new_ax(figsize=(7, 5.2))
    # 斜面（30°）
    ax.plot([0, 4, 4, 0], [0, 0, 2.31, 0], color=CHALK, lw=2)
    ax.fill([0, 4, 4], [0, 0, 2.31], color=CHALK, alpha=0.06)
    # 物块（贴斜面，中心 M）
    mx, my = 2.0, 1.155
    ax.plot([mx], [my + 0.18], "s", color=YELLOW, ms=22)
    kw = dict(angles="xy", scale_units="xy", scale=1, width=0.011)
    ax.quiver(mx, my + 0.18, 0, -1.4, color=ORANGE, **kw)          # 重力
    ax.quiver(mx, my + 0.18, -0.6, 1.04, color=GREEN, **kw)        # 支持力（垂直斜面）
    ax.quiver(mx, my + 0.18, 0.87, 0.5, color=YELLOW, **kw)        # 摩擦力（物块静止/有下滑趋势：沿斜面向上）
    ax.annotate("重力 G", (mx + 0.1, my - 1.15), color=ORANGE, fontsize=13)
    ax.annotate("支持力 N（⊥斜面）", (mx - 1.95, my + 1.35), color=GREEN, fontsize=13)
    ax.annotate("摩擦力 f（沿斜面向上）", (mx + 0.55, my + 0.95), color=YELLOW, fontsize=13)
    ax.annotate("30°", (3.45, 0.12), color=CHALK, fontsize=12)
    ax.set_xlim(-1.2, 5)
    ax.set_ylim(-0.6, 3.4)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("斜面上物块的受力分析", color=CHALK, fontsize=14)
    _save(fig, "physics_incline_forces.png")


# ---------------- 元数据清单 ----------------

MANIFEST = [
    {"file": "math_tangent_secant.png", "media_type": "static", "subject": "math", "topic": "导数",
     "keywords": ["切线", "割线", "导数", "斜率", "微分", "瞬时变化率", "几何意义", "求导"],
     "caption": "割线 PQ 随 Q 靠近 P 逐渐逼近切线，切线斜率即该点导数",
     "llm_desc": "示意图：曲线 y=x² 上 P(1,1) 处的切线与割线 PQ，演示割线逼近切线的过程，适合讲导数的几何意义、瞬时变化率"},
    {"file": "math_extremum.png", "media_type": "static", "subject": "math", "topic": "极值",
     "keywords": ["极值", "极大值", "极小值", "驻点", "导数为零", "单调性", "最值"],
     "caption": "极值点处切线水平，导数为零",
     "llm_desc": "示意图：y=x³−3x 的极大值点与极小值点，两处切线均水平（f′=0），适合讲利用导数求极值、函数单调性"},
    {"file": "math_integral_area.png", "media_type": "static", "subject": "math", "topic": "定积分",
     "keywords": ["定积分", "积分", "面积", "曲边梯形", "微元", "黎曼"],
     "caption": "定积分等于曲线与 x 轴围成的面积，由无数个微元累加而成",
     "llm_desc": "示意图：y=x² 在 [0,1] 上曲线下方阴影面积，并标出一个微元矩形 f(x)dx，适合讲定积分的几何意义、微元法"},
    {"file": "math_normal_curves.png", "media_type": "static", "subject": "math", "topic": "正态分布",
     "keywords": ["正态分布", "高斯", "均值", "标准差", "方差", "概率密度", "钟形", "钟型"],
     "caption": "μ 决定曲线中心位置，σ 决定曲线胖瘦",
     "llm_desc": "对比图：三条正态分布密度曲线（σ=1 瘦高、σ=2 矮胖、μ=2 右移），适合讲均值与标准差对分布形态的影响"},
    {"file": "math_exp_log.png", "media_type": "static", "subject": "math", "topic": "指数对数",
     "keywords": ["指数函数", "对数函数", "反函数", "ln", "对称"],
     "caption": "指数函数与对数函数互为反函数，图像关于 y=x 对称",
     "llm_desc": "对比图：y=eˣ 与 y=ln x 的图像及对称轴 y=x，适合讲指数对数的反函数关系与图像性质"},
    {"file": "math_sin_cos.png", "media_type": "static", "subject": "math", "topic": "三角函数",
     "keywords": ["正弦", "余弦", "三角函数", "周期", "相位", "sin", "cos"],
     "caption": "正弦与余弦曲线：周期都是 2π，相位相差 π/2",
     "llm_desc": "对比图：sin x 与 cos x 在 [−2π, 2π] 的图像，标注相位差 π/2，适合讲三角函数图像、周期性、诱导公式"},
    {"file": "math_unit_circle.png", "media_type": "static", "subject": "math", "topic": "单位圆",
     "keywords": ["单位圆", "弧度", "三角函数定义", "终边", "坐标"],
     "caption": "单位圆上点 P 的横坐标是 cos θ，纵坐标是 sin θ",
     "llm_desc": "示意图：单位圆上角 θ 的终边与点 P(cos θ, sin θ)，用颜色分别标出 sin/cos 对应的线段，适合讲三角函数的单位圆定义"},
    {"file": "math_vector_add.png", "media_type": "static", "subject": "math", "topic": "向量",
     "keywords": ["向量", "矢量", "平行四边形", "向量加法", "合成", "三角形法则"],
     "caption": "向量加法的平行四边形法则：对角线即 a+b",
     "llm_desc": "示意图：向量 a、b 及其和向量 a+b 构成平行四边形，适合讲向量加法、力的合成"},
    {"file": "physics_wave.gif", "media_type": "gif", "subject": "physics", "topic": "机械波",
     "keywords": ["波", "机械波", "横波", "波动", "波长", "传播", "波速", "介质"],
     "caption": "横波传播动图：波形向右移动，介质质点（橙点）只上下振动",
     "llm_desc": "动图：正弦波形向右传播，固定位置的橙色质点只做上下振动不随波迁移，适合讲机械波的传播、横波、振动与波动的区别"},
    {"file": "physics_shm.gif", "media_type": "gif", "subject": "physics", "topic": "简谐运动",
     "keywords": ["简谐运动", "简谐振动", "振动", "弹簧振子", "位移", "周期", "振幅", "回复力"],
     "caption": "简谐运动动图：振子往复运动，位移-时间图像是正弦曲线",
     "llm_desc": "动图：左侧弹簧振子上下振动，右侧同步画出其位移-时间正弦曲线，适合讲简谐运动的定义、位移时间图像、周期与振幅"},
    {"file": "physics_projectile.png", "media_type": "static", "subject": "physics", "topic": "平抛运动",
     "keywords": ["平抛", "抛体", "抛物线", "运动的合成", "运动的分解", "自由落体"],
     "caption": "平抛运动：水平方向匀速（绿），竖直方向自由落体（橙）",
     "llm_desc": "示意图：平抛运动的抛物线轨迹，沿途分解出水平匀速分量与竖直加速分量，适合讲运动的合成与分解、平抛运动规律"},
    {"file": "physics_incline_forces.png", "media_type": "static", "subject": "physics", "topic": "受力分析",
     "keywords": ["受力分析", "斜面", "重力", "支持力", "摩擦力", "力的分解"],
     "caption": "静止在斜面上的物块受三个力：重力、垂直斜面的支持力、沿斜面向上的摩擦力",
     "llm_desc": "示意图：30° 斜面上静止的物块及其受力（重力竖直向下、支持力垂直斜面、摩擦力沿斜面向上），适合讲受力分析、力的分解"},
]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("生成黑板风教学插图…")
    fig_tangent_secant()
    fig_extremum()
    fig_integral_area()
    fig_normal_curves()
    fig_exp_log()
    fig_sin_cos()
    fig_unit_circle()
    fig_vector_add()
    gif_wave()
    gif_shm()
    fig_projectile()
    fig_incline_forces()

    for item in MANIFEST:
        item.setdefault("source", "manual")
        item.setdefault("license", "original (script-generated, EduNUWA)")
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"items": MANIFEST}, f, ensure_ascii=False, indent=2)
    print(f"完成：{len(MANIFEST)} 张图 + manifest.json → {OUT_DIR}")


if __name__ == "__main__":
    main()
