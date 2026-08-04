#!/usr/bin/env python3
"""效能基準引擎(CHG-20260804-05)。stdlib `time`,不引入相依。

**為什麼量比值而不是秒數。** 共用的 CI runner 速度會差好幾倍,而且同一台機器在
不同時段也不一樣。拿絕對秒數設門檻,結果是這道閘三不五時無故轉紅——
而**會無故轉紅的閘,人會在第一時間關掉它**。那與沒有閘是同一件事。

所以每一輪都在同一個行程裡先跑一段固定的**校準負載**,再把每個目標的時間
除以校準時間。機器快慢會同時作用在分子與分母上,約掉。剩下的比值才是
「這段程式碼相對於這台機器有多貴」——那是跨機器可比的量。

門檻抓**倍數**(預設 2.0)而不是百分比:要抓的是演算法級退步(O(n) → O(n²)、
把一個迴圈套進另一個迴圈),不是 10% 的排程雜訊。
"""
from __future__ import annotations
import time

DEFAULT_REPEAT = 7          # 取最小值:雜訊只會加時間,不會減——見 measure()
DEFAULT_TOLERANCE = 2.0     # 倍數門檻:抓演算法退步,不抓雜訊
CALIBRATION_N = 60000


def _median(xs: list) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def calibration_workload() -> int:
    """固定的純 Python 負載。內容不重要,重要的是它每一輪都一樣。"""
    total = 0
    for i in range(CALIBRATION_N):
        total += (i ^ (i >> 3)) & 0xFF
    return total


def measure(fn, arg, repeat: int = DEFAULT_REPEAT) -> float:
    """回**最小**秒數。先跑一次暖身,讓 import 與快取的成本不算進來。

    原本取中位數。實測在有背景負載時(同時跑 mypy),同一份工作的兩次量測
    差到 4.93 倍——中位數擋得住單一次尖峰,擋不住**持續**的競爭。
    而雜訊只會讓時間變長、不會變短,所以最小值才是「這段程式碼本身有多貴」
    的最佳估計。這是被自己的綠燈穩定性守衛抓出來後改的。
    """
    try:
        fn(arg) if arg is not None else fn()
    except Exception:                       # noqa: BLE001 —— 基準不負責驗正確性
        pass
    samples = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        try:
            fn(arg) if arg is not None else fn()
        except Exception:                   # noqa: BLE001
            pass
        samples.append(time.perf_counter() - t0)
    return min(samples)


def run_bench(targets, repeat: int = DEFAULT_REPEAT) -> dict:
    """targets: [(名稱, 函式, 參數)]。回含比值的報告。

    校準**每個目標前都重跑一次**。原本只在整輪開頭校準一次——但機器負載會在
    一輪之內變化,那時分子與分母不再來自同一個時刻,約不掉。
    """
    cal = measure(calibration_workload, None, repeat)
    if cal <= 0:
        # 校準量到 0 秒代表計時器解析度不夠,比值會變成無限大或除零——
        # 這種情況要回報,不能靜默產出一份看起來正常的報告
        return {"version": 1, "error": "校準負載量到 0 秒:計時器解析度不足",
                "calibration_s": cal, "targets": {}}
    out = {}
    for name, fn, arg in targets:
        near_cal = measure(calibration_workload, None, max(3, repeat // 2))
        secs = measure(fn, arg, repeat)
        base = min(cal, near_cal) if near_cal > 0 else cal
        out[name] = {"min_s": round(secs, 9), "ratio": round(secs / base, 6)}
    return {"version": 1, "repeat": repeat, "calibration_s": round(cal, 9),
            "_ratio_doc": "ratio = 本目標的中位數秒數 / 同一輪校準負載的中位數秒數。"
                          "機器快慢在分子分母上約掉,故跨機器可比。",
            "targets": out}
