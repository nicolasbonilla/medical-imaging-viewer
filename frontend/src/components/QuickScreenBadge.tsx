/**
 * QuickScreenBadge — Browser-based brain MRI screening using ONNX Runtime Web.
 *
 * Extracts the current axial slice, sends it to a Web Worker for classification,
 * and displays a normal/abnormal badge. All inference runs locally — no data
 * leaves the browser.
 *
 * IMPORTANT: This is an assistive screening tool, NOT a diagnostic device.
 * A clear disclaimer is always shown.
 *
 * @module components/QuickScreenBadge
 */

import React, { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useEdgeAI, type ScreeningResult } from '@/hooks/useEdgeAI';

interface QuickScreenBadgeProps {
  /** Current slice pixel data as base64 PNG string (data:image/png;base64,...) */
  currentSliceBase64: string;
  /** Image width in pixels */
  imageWidth: number;
  /** Image height in pixels */
  imageHeight: number;
}

export const QuickScreenBadge: React.FC<QuickScreenBadgeProps> = ({
  currentSliceBase64,
  imageWidth,
  imageHeight,
}) => {
  const { t } = useTranslation();
  const {
    classify,
    isModelLoaded,
    isModelLoading,
    isClassifying,
    result,
    error,
    isModelAvailable,
    reset,
  } = useEdgeAI();

  const [showDisclaimer, setShowDisclaimer] = useState(false);

  // Extract grayscale pixel data from base64 PNG
  const extractPixelData = useCallback(
    (): Promise<Float32Array> =>
      new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => {
          const canvas = document.createElement('canvas');
          canvas.width = imageWidth;
          canvas.height = imageHeight;
          const ctx = canvas.getContext('2d');
          if (!ctx) {
            reject(new Error('Canvas context unavailable'));
            return;
          }
          ctx.drawImage(img, 0, 0, imageWidth, imageHeight);
          const imgData = ctx.getImageData(0, 0, imageWidth, imageHeight);
          const pixels = imgData.data;
          // Convert RGBA to grayscale Float32
          const grayscale = new Float32Array(imageWidth * imageHeight);
          for (let i = 0; i < grayscale.length; i++) {
            const r = pixels[i * 4];
            const g = pixels[i * 4 + 1];
            const b = pixels[i * 4 + 2];
            grayscale[i] = 0.299 * r + 0.587 * g + 0.114 * b;
          }
          resolve(grayscale);
        };
        img.onerror = () => reject(new Error('Failed to decode slice image'));
        img.src = currentSliceBase64;
      }),
    [currentSliceBase64, imageWidth, imageHeight],
  );

  const handleScreen = useCallback(async () => {
    try {
      const pixelData = await extractPixelData();
      classify(pixelData, imageWidth, imageHeight);
    } catch (err: any) {
      console.error('[QuickScreen]', err);
    }
  }, [extractPixelData, classify, imageWidth, imageHeight]);

  // Model not available — don't show anything
  if (isModelAvailable === false) {
    return null;
  }

  const isProcessing = isModelLoading || isClassifying;

  return (
    <div className="flex flex-col items-end gap-1">
      {/* Result badge */}
      {result && <ResultBadge result={result} onDismiss={reset} t={t} />}

      {/* Quick Screen button */}
      <button
        onClick={handleScreen}
        disabled={isProcessing}
        className="flex items-center gap-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-white border border-gray-600 transition-colors"
        style={{ height: 28, padding: '0 10px', borderRadius: 6, fontSize: 12, fontWeight: 500 }}
        title={t('edgeAI.quickScreen', 'Quick Screen')}
      >
        {isProcessing ? (
          <>
            <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            <span>
              {isModelLoading
                ? t('edgeAI.loadingModel', 'Loading model...')
                : t('edgeAI.classifying', 'Analyzing...')}
            </span>
          </>
        ) : (
          <>
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
              />
            </svg>
            <span>{t('edgeAI.quickScreen', 'Quick Screen')}</span>
          </>
        )}
      </button>

      {/* Disclaimer toggle */}
      {(result || isProcessing) && (
        <button
          onClick={() => setShowDisclaimer(!showDisclaimer)}
          className="text-[10px] text-gray-500 hover:text-gray-400 underline"
        >
          {t('edgeAI.disclaimer', 'Disclaimer')}
        </button>
      )}

      {/* Disclaimer */}
      {showDisclaimer && (
        <div className="border border-yellow-700/50 rounded text-[10px] text-yellow-300/80 leading-tight" style={{ maxWidth: 240, padding: 8, background: '#111827', borderRadius: 6 }}>
          {t(
            'edgeAI.disclaimerText',
            'This is an assistive screening tool only. Results are NOT diagnostic and must be confirmed by a qualified radiologist. All processing runs locally in your browser — no patient data is transmitted.',
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="max-w-[200px] p-1.5 bg-red-900/60 border border-red-800/50 rounded text-[10px] text-red-300">
          {error}
        </div>
      )}
    </div>
  );
};

// --------------------------------------------------------------------------
// Result badge sub-component
// --------------------------------------------------------------------------

function ResultBadge({
  result,
  onDismiss,
  t,
}: {
  result: ScreeningResult;
  onDismiss: () => void;
  t: (key: string, defaultValue: string) => string;
}) {
  const isNormal = result.label === 'normal';
  const confidence = (result.confidence * 100).toFixed(1);

  return (
    <div
      className={`flex items-center border ${
        isNormal
          ? 'bg-green-900/70 border-green-700 text-green-200'
          : 'bg-red-900/70 border-red-700 text-red-200'
      }`}
      style={{ gap: 8, padding: '6px 12px', borderRadius: 6 }}
    >
      {/* Icon */}
      {isNormal ? (
        <svg className="w-4 h-4 text-green-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ) : (
        <svg className="w-4 h-4 text-red-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
      )}

      <div className="flex flex-col">
        <span className="text-xs font-semibold">
          {isNormal
            ? t('edgeAI.resultNormal', 'Normal')
            : t('edgeAI.resultAbnormal', 'Review Recommended')}
        </span>
        <span className="text-[10px] opacity-70">
          {confidence}% | {result.inferenceTimeMs}ms
        </span>
      </div>

      {/* Dismiss */}
      <button
        onClick={onDismiss}
        className="ml-1 p-0.5 hover:bg-white/10 rounded"
        title={t('common.close', 'Close')}
      >
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

export default QuickScreenBadge;
