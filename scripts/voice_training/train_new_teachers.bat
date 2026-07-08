@echo off
REM 批量训练6位新教师专属GPT音色（GPU加速，每位约30-60分钟）
echo ============================================
echo   批量训练新教师GPT音色
echo ============================================
echo.

set TEACHERS=T007 T008 T009 T010 T011 T012
set DATA=data/teachers

REM T007: 示范教师07 中国哲学
echo [1/6] 示范教师07 (中国哲学)...
python scripts/voice_training/train_gpt.py T007 --list %DATA%/T_20260612_001/voice/train/T007.list --wav-dir %DATA%/T_20260612_001/audio_samples --epochs 20
echo.

REM T008: 示范教师08 大学物理
echo [2/6] 示范教师08 (大学物理)...
python scripts/voice_training/train_gpt.py T008 --list %DATA%/T_20260612_002/voice/train/T008.list --wav-dir %DATA%/T_20260612_002/audio_samples --epochs 20
echo.

REM T009: 植物学 某高校
echo [3/6] 植物学 (某高校)...
python scripts/voice_training/train_gpt.py T009 --list %DATA%/T_20260612_003/voice/train/T009.list --wav-dir %DATA%/T_20260612_003/audio_samples --epochs 20
echo.

REM T010: 管理学 某高校
echo [4/6] 管理学 (某高校)...
python scripts/voice_training/train_gpt.py T010 --list %DATA%/T_20260612_004/voice/train/T010.list --wav-dir %DATA%/T_20260612_004/audio_samples --epochs 20
echo.

REM T011: 经济学 某高校
echo [5/6] 经济学 (某高校)...
python scripts/voice_training/train_gpt.py T011 --list %DATA%/T_20260612_005/voice/train/T011.list --wav-dir %DATA%/T_20260612_005/audio_samples --epochs 20
echo.

REM T012: 示范教师12 食品化学
echo [6/6] 示范教师12 (食品化学)...
python scripts/voice_training/train_gpt.py T012 --list %DATA%/T_20260612_006/voice/train/T012.list --wav-dir %DATA%/T_20260612_006/audio_samples --epochs 20

echo.
echo ============================================
echo   训练完成! 下一步:
echo   python scripts/voice_training/finalize_voice.py T_20260612_001 --exp T007
echo   ... (对每位教师执行)
echo ============================================
pause
