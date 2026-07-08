// Canvas-based placeholder avatar — draws a simple face with mouth driven by mouthOpen (0-1)
import { useRef, useEffect } from 'react';
import './Live2DStage.css';

interface Live2DStageProps {
  mouthOpen: number;
  teacherName?: string;
}

export function Live2DStage({ mouthOpen, teacherName }: Live2DStageProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;
    const cx = w / 2;
    const cy = h * 0.3;
    const radius = 75;

    ctx.clearRect(0, 0, w, h);

    // Background
    ctx.fillStyle = '#f0f4f8';
    ctx.fillRect(0, 0, w, h);

    // Body / shoulders
    ctx.fillStyle = '#3a5a8c';
    ctx.beginPath();
    ctx.ellipse(cx, cy + radius + 60, 70, 80, 0, 0, Math.PI * 2);
    ctx.fill();

    // Head
    ctx.fillStyle = '#ffe4c4';
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fill();

    // Hair
    ctx.fillStyle = '#2a2a2a';
    ctx.beginPath();
    ctx.arc(cx, cy - 8, radius + 4, Math.PI, Math.PI * 2);
    ctx.fill();

    // Eyes
    ctx.fillStyle = '#fff';
    ctx.beginPath();
    ctx.ellipse(cx - 22, cy - 5, 12, 8, 0, 0, Math.PI * 2);
    ctx.ellipse(cx + 22, cy - 5, 12, 8, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#222';
    ctx.beginPath();
    ctx.arc(cx - 22, cy - 4, 5, 0, Math.PI * 2);
    ctx.arc(cx + 22, cy - 4, 5, 0, Math.PI * 2);
    ctx.fill();

    // Eyebrows
    ctx.strokeStyle = '#333';
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(cx - 34, cy - 16);
    ctx.lineTo(cx - 14, cy - 18);
    ctx.moveTo(cx + 14, cy - 18);
    ctx.lineTo(cx + 34, cy - 16);
    ctx.stroke();

    // Mouth — height driven by mouthOpen
    const mouthY = cy + 28;
    const mouthHeight = 3 + mouthOpen * 22;
    ctx.fillStyle = '#c44';
    ctx.beginPath();
    ctx.ellipse(cx, mouthY, 16, Math.max(mouthHeight, 2), 0, 0, Math.PI * 2);
    ctx.fill();

  }, [mouthOpen]);

  return (
    <div className="live2d-stage">
      <canvas ref={canvasRef} width={280} height={420} className="live2d-canvas" />
      {teacherName && <p className="live2d-teacher-name">{teacherName}</p>}
      <p className="live2d-stub-label">Live2D Placeholder</p>
    </div>
  );
}
