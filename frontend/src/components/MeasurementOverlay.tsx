/**
 * Measurement Overlay for 2D Viewer.
 *
 * Provides ruler (distance), angle, and elliptical ROI measurement tools
 * as a transparent overlay on top of the medical image canvas.
 * Measurements are displayed in mm using the image's REAL in-plane voxel spacing
 * (`pixelSpacing` [row, col] mm, threaded from the header). Falls back to 1mm/px only
 * when the header spacing is unavailable — never assume 1mm on anisotropic data.
 *
 * @module components/MeasurementOverlay
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { Ruler, Triangle, Circle, Trash2, X } from 'lucide-react';
import { useViewerStore } from '@/store/useViewerStore';

interface Point { x: number; y: number }

interface Measurement {
  id: string;
  type: 'ruler' | 'angle' | 'ellipse';
  points: Point[];
  value?: string;
  sliceIndex: number;
}

interface MeasurementOverlayProps {
  imageWidth: number;
  imageHeight: number;
  canvasWidth: number;
  canvasHeight: number;
  sliceIndex: number;
  zoomLevel: number;
  panOffset: { x: number; y: number };
  pixelSpacing?: [number, number]; // mm per pixel [row, col], default [1,1]
}

export default function MeasurementOverlay({
  imageWidth,
  imageHeight,
  canvasWidth,
  canvasHeight,
  sliceIndex,
  zoomLevel,
  panOffset,
  pixelSpacing = [1, 1],
}: MeasurementOverlayProps) {
  const activeTool = useViewerStore((s) => s.measurementTool);
  const setActiveTool = useViewerStore((s) => s.setMeasurementTool);
  const clearSignal = useViewerStore((s) => s.measurementClearSignal);
  const [measurements, setMeasurements] = useState<Measurement[]>([]);
  const [currentPoints, setCurrentPoints] = useState<Point[]>([]);
  const [isDrawing, setIsDrawing] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);

  // Clear all measurements when signal changes
  useEffect(() => {
    if (clearSignal > 0) {
      setMeasurements([]);
      setCurrentPoints([]);
      setIsDrawing(false);
    }
  }, [clearSignal]);

  // Scale factors: image coords → canvas coords
  const scaleX = canvasWidth / imageWidth;
  const scaleY = canvasHeight / imageHeight;

  const toCanvas = useCallback((p: Point): Point => ({
    x: p.x * scaleX,
    y: p.y * scaleY,
  }), [scaleX, scaleY]);

  const toImage = useCallback((canvasX: number, canvasY: number): Point => ({
    x: canvasX / scaleX,
    y: canvasY / scaleY,
  }), [scaleX, scaleY]);

  const getMousePos = useCallback((e: React.MouseEvent): Point => {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const rect = svg.getBoundingClientRect();
    return toImage(e.clientX - rect.left, e.clientY - rect.top);
  }, [toImage]);

  // Distance in mm
  const calcDistance = useCallback((p1: Point, p2: Point): number => {
    const dx = (p2.x - p1.x) * pixelSpacing[1];
    const dy = (p2.y - p1.y) * pixelSpacing[0];
    return Math.sqrt(dx * dx + dy * dy);
  }, [pixelSpacing]);

  // Angle in degrees
  const calcAngle = useCallback((p1: Point, p2: Point, p3: Point): number => {
    const v1 = { x: p1.x - p2.x, y: p1.y - p2.y };
    const v2 = { x: p3.x - p2.x, y: p3.y - p2.y };
    const dot = v1.x * v2.x + v1.y * v2.y;
    const mag1 = Math.sqrt(v1.x * v1.x + v1.y * v1.y);
    const mag2 = Math.sqrt(v2.x * v2.x + v2.y * v2.y);
    if (mag1 === 0 || mag2 === 0) return 0;
    const cos = Math.max(-1, Math.min(1, dot / (mag1 * mag2)));
    return Math.acos(cos) * (180 / Math.PI);
  }, []);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (!activeTool) return;
    e.stopPropagation();
    const pos = getMousePos(e);
    setCurrentPoints([pos]);
    setIsDrawing(true);
  }, [activeTool, getMousePos]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDrawing || !activeTool) return;
    e.stopPropagation();
    const pos = getMousePos(e);

    if (activeTool === 'ruler') {
      setCurrentPoints(prev => [prev[0], pos]);
    } else if (activeTool === 'angle') {
      setCurrentPoints(prev => {
        if (prev.length === 1) return [prev[0], pos];
        if (prev.length === 2) return [prev[0], prev[1], pos];
        return prev;
      });
    } else if (activeTool === 'ellipse') {
      setCurrentPoints(prev => [prev[0], pos]);
    }
  }, [isDrawing, activeTool, getMousePos]);

  const handleMouseUp = useCallback((e: React.MouseEvent) => {
    if (!isDrawing || !activeTool) return;
    e.stopPropagation();
    const pos = getMousePos(e);

    if (activeTool === 'ruler' && currentPoints.length >= 1) {
      const p1 = currentPoints[0];
      const dist = calcDistance(p1, pos);
      const m: Measurement = {
        id: `m-${Date.now()}`,
        type: 'ruler',
        points: [p1, pos],
        value: `${dist.toFixed(1)} mm`,
        sliceIndex,
      };
      setMeasurements(prev => [...prev, m]);
      setCurrentPoints([]);
      setIsDrawing(false);
    } else if (activeTool === 'angle') {
      if (currentPoints.length === 1) {
        // Second point placed — wait for third
        setCurrentPoints([currentPoints[0], pos]);
      } else if (currentPoints.length >= 2) {
        const angle = calcAngle(currentPoints[0], currentPoints[1], pos);
        const m: Measurement = {
          id: `m-${Date.now()}`,
          type: 'angle',
          points: [currentPoints[0], currentPoints[1], pos],
          value: `${angle.toFixed(1)}°`,
          sliceIndex,
        };
        setMeasurements(prev => [...prev, m]);
        setCurrentPoints([]);
        setIsDrawing(false);
      }
    } else if (activeTool === 'ellipse' && currentPoints.length >= 1) {
      const p1 = currentPoints[0];
      const rx = Math.abs(pos.x - p1.x) * pixelSpacing[1];
      const ry = Math.abs(pos.y - p1.y) * pixelSpacing[0];
      const area = Math.PI * rx * ry;
      const m: Measurement = {
        id: `m-${Date.now()}`,
        type: 'ellipse',
        points: [p1, pos],
        value: `${area.toFixed(1)} mm²`,
        sliceIndex,
      };
      setMeasurements(prev => [...prev, m]);
      setCurrentPoints([]);
      setIsDrawing(false);
    }
  }, [isDrawing, activeTool, currentPoints, sliceIndex, calcDistance, calcAngle, pixelSpacing, getMousePos]);

  const deleteMeasurement = useCallback((id: string) => {
    setMeasurements(prev => prev.filter(m => m.id !== id));
  }, []);

  const clearAll = useCallback(() => {
    setMeasurements([]);
    setCurrentPoints([]);
    setIsDrawing(false);
  }, []);

  // Filter measurements for current slice
  const visibleMeasurements = measurements.filter(m => m.sliceIndex === sliceIndex);

  // Toolbar moved to ViewerApp toolbar bar — only render SVG overlay when needed
  if (!activeTool && visibleMeasurements.length === 0) {
    return null;
  }

  return (
    <>
      {/* SVG overlay for drawing measurements — toolbar is in ViewerApp */}
      <svg
        ref={svgRef}
        className="absolute inset-0 z-10"
        width={canvasWidth}
        height={canvasHeight}
        style={{ cursor: activeTool ? 'crosshair' : 'default', pointerEvents: activeTool ? 'all' : 'none' }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
      >
        {/* Existing measurements */}
        {visibleMeasurements.map(m => (
          <MeasurementGraphic key={m.id} measurement={m} toCanvas={toCanvas} onDelete={deleteMeasurement} />
        ))}

        {/* Current drawing */}
        {isDrawing && currentPoints.length > 0 && activeTool === 'ruler' && currentPoints.length === 2 && (
          <RulerGraphic p1={toCanvas(currentPoints[0])} p2={toCanvas(currentPoints[1])} label="" />
        )}
        {isDrawing && activeTool === 'angle' && currentPoints.length >= 2 && (
          <AngleGraphic points={currentPoints.map(toCanvas)} label="" />
        )}
        {isDrawing && activeTool === 'ellipse' && currentPoints.length === 2 && (
          <EllipseGraphic p1={toCanvas(currentPoints[0])} p2={toCanvas(currentPoints[1])} label="" />
        )}
      </svg>
    </>
  );
}

// ─── SVG Primitives ───

function RulerGraphic({ p1, p2, label }: { p1: Point; p2: Point; label: string }) {
  const mx = (p1.x + p2.x) / 2;
  const my = (p1.y + p2.y) / 2;
  return (
    <g>
      <line x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke="#FBBF24" strokeWidth={1.5} strokeDasharray="4 2" />
      <circle cx={p1.x} cy={p1.y} r={3} fill="#FBBF24" />
      <circle cx={p2.x} cy={p2.y} r={3} fill="#FBBF24" />
      {label && (
        <text x={mx} y={my - 8} fill="#FBBF24" fontSize={11} fontWeight="bold" textAnchor="middle"
          stroke="black" strokeWidth={2} paintOrder="stroke">{label}</text>
      )}
    </g>
  );
}

function AngleGraphic({ points, label }: { points: Point[]; label: string }) {
  if (points.length < 2) return null;
  return (
    <g>
      <line x1={points[0].x} y1={points[0].y} x2={points[1].x} y2={points[1].y} stroke="#34D399" strokeWidth={1.5} />
      {points.length >= 3 && (
        <line x1={points[1].x} y1={points[1].y} x2={points[2].x} y2={points[2].y} stroke="#34D399" strokeWidth={1.5} />
      )}
      {points.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r={3} fill="#34D399" />)}
      {label && points.length >= 3 && (
        <text x={points[1].x + 12} y={points[1].y - 8} fill="#34D399" fontSize={11} fontWeight="bold"
          stroke="black" strokeWidth={2} paintOrder="stroke">{label}</text>
      )}
    </g>
  );
}

function EllipseGraphic({ p1, p2, label }: { p1: Point; p2: Point; label: string }) {
  const cx = (p1.x + p2.x) / 2;
  const cy = (p1.y + p2.y) / 2;
  const rx = Math.abs(p2.x - p1.x) / 2;
  const ry = Math.abs(p2.y - p1.y) / 2;
  return (
    <g>
      <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="none" stroke="#60A5FA" strokeWidth={1.5} strokeDasharray="4 2" />
      {label && (
        <text x={cx} y={cy} fill="#60A5FA" fontSize={11} fontWeight="bold" textAnchor="middle"
          stroke="black" strokeWidth={2} paintOrder="stroke">{label}</text>
      )}
    </g>
  );
}

function MeasurementGraphic({ measurement, toCanvas, onDelete }: {
  measurement: Measurement;
  toCanvas: (p: Point) => Point;
  onDelete: (id: string) => void;
}) {
  const pts = measurement.points.map(toCanvas);

  if (measurement.type === 'ruler' && pts.length >= 2) {
    return (
      <g style={{ cursor: 'pointer' }} onClick={() => onDelete(measurement.id)}>
        <RulerGraphic p1={pts[0]} p2={pts[1]} label={measurement.value || ''} />
      </g>
    );
  }

  if (measurement.type === 'angle' && pts.length >= 3) {
    return (
      <g style={{ cursor: 'pointer' }} onClick={() => onDelete(measurement.id)}>
        <AngleGraphic points={pts} label={measurement.value || ''} />
      </g>
    );
  }

  if (measurement.type === 'ellipse' && pts.length >= 2) {
    return (
      <g style={{ cursor: 'pointer' }} onClick={() => onDelete(measurement.id)}>
        <EllipseGraphic p1={pts[0]} p2={pts[1]} label={measurement.value || ''} />
      </g>
    );
  }

  return null;
}
