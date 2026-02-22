/**
 * ReportViewerModal - Professional full-screen medical report viewer.
 *
 * Renders AI-generated radiology reports with:
 * - react-markdown for proper markdown rendering
 * - Patient demographics bar (RSNA structured reporting)
 * - Professional medical document typography (serif body, sans headings)
 * - Print support (window.print + @media print CSS for A4)
 * - Copy to clipboard
 * - HIPAA compliance disclaimer
 *
 * Follows MAGNIMS/RSNA/McDonald 2017 standards for MS MRI reporting.
 *
 * @module components/ReportViewerModal
 */

import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { AnimatePresence, motion } from 'framer-motion';
import { Printer, Copy, Check, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ReportResponse } from '@/types';

interface ReportViewerModalProps {
  report: ReportResponse;
  isOpen: boolean;
  onClose: () => void;
  patientName?: string;
  patientMRN?: string;
  patientAge?: number;
  patientSex?: string;
  studyDate?: string;
  studyDescription?: string;
  institutionName?: string;
}

export function ReportViewerModal({
  report,
  isOpen,
  onClose,
  patientName,
  patientMRN,
  patientAge,
  patientSex,
  studyDate,
  studyDescription,
  institutionName,
}: ReportViewerModalProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  // Escape key handler
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Copy to clipboard
  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(report.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = report.content;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [report.content]);

  const handlePrint = useCallback(() => {
    window.print();
  }, []);

  const templateLabel = report.template_type
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return '---';
    try {
      return new Date(dateStr).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      });
    } catch {
      return dateStr;
    }
  };

  const generatedAt = new Date().toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="report-print-root fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm print:bg-white print:static print:backdrop-blur-none"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.96, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.96, opacity: 0, y: 20 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="relative flex flex-col bg-gray-100 rounded-xl shadow-2xl overflow-hidden w-[92vw] h-[92vh] max-w-6xl print:w-full print:h-auto print:shadow-none print:rounded-none print:max-w-none"
            onClick={(e) => e.stopPropagation()}
          >
            {/* ACTION BAR */}
            <div className="report-action-bar flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200 flex-shrink-0 print:hidden">
              <div className="flex items-center gap-3">
                <span className="px-3 py-1 bg-amber-100 text-amber-800 rounded-full text-xs font-semibold tracking-wide">
                  {templateLabel}
                </span>
                <span className="px-2.5 py-1 bg-gray-100 text-gray-600 rounded-full text-xs font-medium border border-gray-200">
                  {report.language.toUpperCase()}
                </span>
                <span className="text-xs text-gray-400">
                  {report.processing_time_ms}ms
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handlePrint}
                  className="flex items-center gap-1.5 px-4 py-2 bg-gray-900 hover:bg-gray-800 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  <Printer className="w-4 h-4" />
                  {t('reportViewer.print')}
                </button>
                <button
                  onClick={handleCopy}
                  className="flex items-center gap-1.5 px-4 py-2 bg-white hover:bg-gray-50 text-gray-700 rounded-lg text-sm font-medium transition-colors border border-gray-300"
                >
                  {copied ? (
                    <>
                      <Check className="w-4 h-4 text-green-600" />
                      <span className="text-green-600">{t('report.copied')}</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-4 h-4" />
                      {t('report.copy')}
                    </>
                  )}
                </button>
                <button
                  onClick={onClose}
                  className="p-2 hover:bg-gray-100 rounded-lg transition-colors ml-2"
                  title={t('reportViewer.keyboardHint')}
                >
                  <X className="w-5 h-5 text-gray-500" />
                </button>
              </div>
            </div>

            {/* DOCUMENT AREA */}
            <div className="flex-1 overflow-y-auto bg-gray-100 print:bg-white print:overflow-visible">
              <div className="report-document max-w-4xl mx-auto my-8 bg-white shadow-lg rounded-sm print:shadow-none print:my-0 print:rounded-none print:max-w-none">

                {/* Document Header */}
                <div className="report-header px-12 pt-10 pb-6 border-b-2 border-gray-900">
                  <div className="text-center">
                    <h1 className="text-lg font-bold uppercase tracking-[0.2em] text-gray-900 font-sans">
                      {institutionName || t('reportViewer.institutionName')}
                    </h1>
                    <p className="text-sm text-gray-500 mt-1 tracking-wide font-sans">
                      {t('reportViewer.subtitle')}
                    </p>
                    <div className="w-16 h-0.5 bg-gray-300 mx-auto mt-4" />
                  </div>
                  <div className="flex justify-between text-xs text-gray-500 mt-4 font-sans">
                    <span>{t('reportViewer.reportId')}: {report.report_id.slice(0, 8).toUpperCase()}</span>
                    <span>{t('reportViewer.generatedAt')}: {generatedAt}</span>
                  </div>
                </div>

                {/* Patient Demographics Bar */}
                <div className="report-demographics px-12 py-4 bg-gray-50 border-b border-gray-300">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <DemoField label={t('reportViewer.patientLabel')} value={patientName || '---'} bold />
                    <DemoField label={t('reportViewer.mrnLabel')} value={patientMRN || '---'} />
                    <DemoField label={t('reportViewer.ageSexLabel')} value={`${patientAge != null ? `${patientAge} yr` : '---'} / ${patientSex || '---'}`} />
                    <DemoField label={t('reportViewer.studyDateLabel')} value={formatDate(studyDate)} />
                  </div>
                  {studyDescription && (
                    <div className="mt-3 pt-3 border-t border-gray-200">
                      <DemoField label={t('reportViewer.studyDescLabel')} value={studyDescription} />
                    </div>
                  )}
                </div>

                {/* Report Body — Rendered Markdown */}
                <div className="report-body px-12 py-8">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      h1: ({ children }) => (
                        <h1 className="text-base font-bold uppercase tracking-wider text-gray-900 text-center border-b-2 border-gray-400 pb-3 mb-6 mt-2 font-sans">
                          {children}
                        </h1>
                      ),
                      h2: ({ children }) => (
                        <h2 className="report-section-heading text-[13px] font-bold uppercase tracking-wider text-gray-800 pb-1.5 mb-3 mt-8 border-b border-gray-200 font-sans">
                          {children}
                        </h2>
                      ),
                      h3: ({ children }) => (
                        <h3 className="text-sm font-semibold text-gray-800 mb-2 mt-5 font-sans">
                          {children}
                        </h3>
                      ),
                      h4: ({ children }) => (
                        <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-700 mb-1.5 mt-4 font-sans">
                          {children}
                        </h4>
                      ),
                      p: ({ children }) => (
                        <p className="text-[13px] text-gray-700 leading-[1.85] mb-3 font-serif">
                          {children}
                        </p>
                      ),
                      ul: ({ children }) => (
                        <ul className="list-disc list-outside ml-5 mb-3 space-y-1">
                          {children}
                        </ul>
                      ),
                      ol: ({ children }) => (
                        <ol className="list-decimal list-outside ml-5 mb-3 space-y-1">
                          {children}
                        </ol>
                      ),
                      li: ({ children }) => (
                        <li className="text-[13px] text-gray-700 leading-relaxed font-serif">
                          {children}
                        </li>
                      ),
                      strong: ({ children }) => (
                        <strong className="font-bold text-gray-900">{children}</strong>
                      ),
                      em: ({ children }) => (
                        <em className="italic text-gray-600">{children}</em>
                      ),
                      hr: () => (
                        <hr className="my-6 border-gray-200" />
                      ),
                      table: ({ children }) => (
                        <div className="overflow-x-auto mb-4 mt-2">
                          <table className="w-full text-sm border-collapse border border-gray-300">
                            {children}
                          </table>
                        </div>
                      ),
                      thead: ({ children }) => (
                        <thead className="bg-gray-100">{children}</thead>
                      ),
                      th: ({ children }) => (
                        <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-gray-700 border border-gray-300 font-sans">
                          {children}
                        </th>
                      ),
                      td: ({ children }) => (
                        <td className="px-3 py-2 text-sm text-gray-700 border border-gray-300 font-serif">
                          {children}
                        </td>
                      ),
                      blockquote: ({ children }) => (
                        <blockquote className="border-l-4 border-amber-400 pl-4 py-1 my-3 bg-amber-50/50 rounded-r">
                          {children}
                        </blockquote>
                      ),
                    }}
                  >
                    {report.content}
                  </ReactMarkdown>
                </div>

                {/* Footer */}
                <div className="report-footer px-12 py-6 border-t-2 border-gray-900 bg-gray-50">
                  <div className="mb-4">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-gray-700 mb-1.5 font-sans">
                      {t('reportViewer.aiDisclaimer')}
                    </h4>
                    <p className="text-xs text-gray-500 leading-relaxed font-serif">
                      {t('reportViewer.aiDisclaimerText')}
                    </p>
                  </div>
                  <div className="flex flex-wrap justify-between text-[10px] text-gray-400 pt-3 border-t border-gray-300 font-sans gap-y-1">
                    <span>{t('reportViewer.model')}: {report.model || 'Claude'}</span>
                    <span>{t('reportViewer.processingTime')}: {report.processing_time_ms}ms</span>
                    {report.tokens_used && (
                      <span>{t('reportViewer.tokens')}: {report.tokens_used.input} in / {report.tokens_used.output} out</span>
                    )}
                  </div>
                  <p className="text-center text-[9px] text-gray-400 mt-4 leading-relaxed font-sans">
                    {t('reportViewer.hipaaNote')}
                  </p>
                </div>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function DemoField({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <div>
      <span className="text-[10px] text-gray-500 uppercase tracking-wider font-sans block">{label}</span>
      <p className={`text-sm text-gray-900 ${bold ? 'font-bold' : 'font-semibold'} mt-0.5 font-sans`}>{value}</p>
    </div>
  );
}

export default ReportViewerModal;
