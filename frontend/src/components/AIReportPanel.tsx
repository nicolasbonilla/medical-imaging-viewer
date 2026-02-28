/**
 * AIReportPanel - Brain MRI Report Generation Panel.
 *
 * Allows users to generate structured radiology reports using Claude API.
 * Features:
 * - Template selection (general, stroke, tumor, dementia)
 * - Language selection (en, es, de)
 * - Clinical findings input
 * - Integrates volumetry data when available
 * - Report viewer with copy/export
 *
 * @module components/AIReportPanel
 */

import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery } from '@tanstack/react-query';
import { aiReportAPI } from '@/api/aiReport';
import { segmentationAPI } from '@/api/segmentation';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import type {
  ReportTemplateType,
  ReportGenerateRequest,
  ReportResponse,
  ReportTemplateInfo,
} from '@/types';

interface AIReportPanelProps {
  volumetry?: Record<string, any> | null;
  patientAge?: number;
  patientSex?: 'M' | 'F';
  onReportGenerated?: (report: ReportResponse) => void;
}

export const AIReportPanel: React.FC<AIReportPanelProps> = ({
  volumetry,
  patientAge,
  patientSex,
  onReportGenerated,
}) => {
  const { t, i18n } = useTranslation();
  const [template, setTemplate] = useState<ReportTemplateType>('general');
  const [language, setLanguage] = useState(i18n.language || 'en');
  const [indication, setIndication] = useState('');
  const [technique, setTechnique] = useState('');
  const [observations, setObservations] = useState('');
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [copied, setCopied] = useState(false);

  // Fetch available templates
  const { data: templates } = useQuery({
    queryKey: ['report-templates'],
    queryFn: () => aiReportAPI.listTemplates(),
    staleTime: 60 * 60 * 1000, // 1 hour
  });

  // Generate report mutation
  const generateMutation = useMutation({
    mutationFn: (req: ReportGenerateRequest) => aiReportAPI.generateReport(req),
    onSuccess: (data) => {
      setReport(data);
      onReportGenerated?.(data);
    },
  });

  const handleGenerate = async () => {
    const findings: Record<string, any> = {};
    if (indication) findings.clinical_indication = indication;
    if (technique) findings.technique = technique;
    if (observations) findings.additional_observations = observations;
    if (patientAge) findings.patient_age = patientAge;
    if (patientSex) findings.patient_sex = patientSex;

    // Auto-collect lesion analysis and DIS data from active segmentation
    const activeSegId = useSegmentationStore.getState().currentSegmentation?.segmentation_id;
    if (activeSegId) {
      try {
        const [lesionData, disData] = await Promise.all([
          segmentationAPI.analyzeLesions(activeSegId).catch(() => null),
          segmentationAPI.getDISAssessment(activeSegId).catch(() => null),
        ]);
        if (lesionData) {
          findings.lesion_analysis = lesionData;
        }
        if (disData) {
          findings.dis_assessment = disData;
        }
      } catch {
        // Continue without lesion data if fetch fails
      }
    }

    generateMutation.mutate({
      template_type: template,
      language,
      findings,
      volumetry: volumetry || null,
    });
  };

  const handleCopy = async () => {
    if (!report) return;
    try {
      await navigator.clipboard.writeText(report.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = report.content;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleReset = () => {
    setReport(null);
    generateMutation.reset();
  };

  const templateIcons: Record<ReportTemplateType, string> = {
    general: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z',
    ms_activity: 'M13 10V3L4 14h7v7l9-11h-7z',
    ms_comprehensive: 'M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z',
    ms_lesion_burden: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
    ms_longitudinal: 'M13 7h8m0 0v8m0-8l-8 8-4-4-6 6',
  };

  return (
    <div className="space-y-3">
          {/* Report not yet generated */}
          {!report && (
            <>
              {/* Template selection */}
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                  {t('report.template', 'Template')}
                </label>
                <div className="grid grid-cols-2 gap-1">
                  {(templates ?? [
                    { id: 'general', name: t('report.templates.general', 'General'), description: '' },
                    { id: 'ms_activity', name: t('report.templates.ms_activity', 'MS Activity'), description: '' },
                    { id: 'ms_lesion_burden', name: t('report.templates.ms_lesion_burden', 'Lesion Burden'), description: '' },
                  ] as ReportTemplateInfo[]).map((tmpl) => (
                    <button
                      key={tmpl.id}
                      onClick={() => setTemplate(tmpl.id)}
                      className={`px-2 py-1.5 rounded text-xs font-medium transition-colors flex items-center gap-1.5 ${
                        template === tmpl.id
                          ? 'bg-amber-500 text-white shadow-sm'
                          : 'bg-white/60 dark:bg-gray-800/60 hover:bg-white dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 border border-gray-200/50 dark:border-gray-700/50'
                      }`}
                      title={tmpl.description}
                    >
                      <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={templateIcons[tmpl.id] || templateIcons.general} />
                      </svg>
                      <span className="truncate">{tmpl.name}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Language selection */}
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                  {t('report.language', 'Language')}
                </label>
                <div className="flex gap-1">
                  {[
                    { code: 'en', label: 'EN' },
                    { code: 'es', label: 'ES' },
                    { code: 'de', label: 'DE' },
                  ].map((lang) => (
                    <button
                      key={lang.code}
                      onClick={() => setLanguage(lang.code)}
                      className={`flex-1 px-2 py-1 rounded text-xs transition-colors ${
                        language === lang.code
                          ? 'bg-amber-500 text-white'
                          : 'bg-white/60 dark:bg-gray-800/60 hover:bg-white dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 border border-gray-200/50 dark:border-gray-700/50'
                      }`}
                    >
                      {lang.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Clinical indication */}
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                  {t('report.indication', 'Clinical Indication')}
                </label>
                <input
                  type="text"
                  value={indication}
                  onChange={(e) => setIndication(e.target.value)}
                  placeholder={t('report.indicationPlaceholder', 'e.g., Headache, rule out mass')}
                  className="w-full px-2 py-1.5 bg-white/80 dark:bg-gray-800/80 border border-gray-200 dark:border-gray-700 rounded text-xs text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:border-amber-500"
                />
              </div>

              {/* Technique */}
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                  {t('report.technique', 'Technique/Sequences')}
                </label>
                <input
                  type="text"
                  value={technique}
                  onChange={(e) => setTechnique(e.target.value)}
                  placeholder={t('report.techniquePlaceholder', 'e.g., T1, T2, FLAIR, DWI, Gd+')}
                  className="w-full px-2 py-1.5 bg-white/80 dark:bg-gray-800/80 border border-gray-200 dark:border-gray-700 rounded text-xs text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:border-amber-500"
                />
              </div>

              {/* Additional observations */}
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                  {t('report.observations', 'Additional Observations')}
                </label>
                <textarea
                  value={observations}
                  onChange={(e) => setObservations(e.target.value)}
                  placeholder={t('report.observationsPlaceholder', 'Any additional findings or context...')}
                  rows={2}
                  className="w-full px-2 py-1.5 bg-white/80 dark:bg-gray-800/80 border border-gray-200 dark:border-gray-700 rounded text-xs text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:border-amber-500 resize-none"
                />
              </div>

              {/* Active segmentation indicator — lesion data will be auto-collected */}
              {useSegmentationStore.getState().currentSegmentation && (
                <div className="flex items-center gap-1.5 px-2 py-1.5 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded">
                  <svg className="w-3.5 h-3.5 text-blue-500 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                  </svg>
                  <span className="text-xs text-blue-700 dark:text-blue-300">
                    {t('report.lesionDataIncluded', 'Lesion analysis data will be auto-collected')}
                  </span>
                </div>
              )}

              {/* Volumetry indicator */}
              {volumetry && (
                <div className="flex items-center gap-1.5 px-2 py-1.5 bg-purple-50 dark:bg-purple-900/30 border border-purple-200 dark:border-purple-800 rounded">
                  <svg className="w-3.5 h-3.5 text-purple-500 dark:text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  <span className="text-xs text-purple-700 dark:text-purple-300">
                    {t('report.volumetryIncluded', 'Volumetry data will be included')}
                  </span>
                </div>
              )}

              {/* Error */}
              {generateMutation.isError && (
                <div className="p-2 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded text-xs text-red-700 dark:text-red-300">
                  {(generateMutation.error as Error)?.message || t('report.generateError', 'Report generation failed')}
                </div>
              )}

              {/* Generate button */}
              <button
                onClick={handleGenerate}
                disabled={generateMutation.isPending}
                className="w-full px-3 py-2 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 shadow-sm"
              >
                {generateMutation.isPending ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                    <span>{t('report.generating', 'Generating...')}</span>
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <span>{t('report.generate', 'Generate Report')}</span>
                  </>
                )}
              </button>
            </>
          )}

          {/* Report generated — compact summary */}
          {report && (
            <>
              {/* Success indicator */}
              <div className="bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-700/50 rounded-lg p-3 text-center">
                <svg className="w-6 h-6 text-green-500 dark:text-green-400 mx-auto mb-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <p className="text-sm text-green-700 dark:text-green-300 font-medium">
                  {t('reportViewer.reportReady', 'Report generated successfully')}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  {report.template_type.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')} | {report.language.toUpperCase()} | {report.processing_time_ms}ms
                </p>
              </div>

              {/* Action buttons */}
              <div className="space-y-1.5">
                <button
                  onClick={() => onReportGenerated?.(report)}
                  className="w-full px-3 py-2.5 bg-amber-500 hover:bg-amber-600 text-white rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 shadow-sm"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  </svg>
                  {t('reportViewer.viewFullReport', 'View Full Report')}
                </button>
                <div className="flex gap-1.5">
                  <button
                    onClick={handleCopy}
                    className="flex-1 px-3 py-1.5 bg-white/60 dark:bg-gray-800/60 hover:bg-white dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 border border-gray-200/50 dark:border-gray-700/50 rounded text-xs transition-colors flex items-center justify-center gap-1"
                  >
                    {copied ? (
                      <>
                        <svg className="w-3.5 h-3.5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                        {t('report.copied', 'Copied!')}
                      </>
                    ) : (
                      <>
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                        </svg>
                        {t('report.copy', 'Copy')}
                      </>
                    )}
                  </button>
                  <button
                    onClick={handleReset}
                    className="flex-1 px-3 py-1.5 bg-white/60 dark:bg-gray-800/60 hover:bg-white dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 border border-gray-200/50 dark:border-gray-700/50 rounded text-xs transition-colors"
                  >
                    {t('report.newReport', 'New Report')}
                  </button>
                </div>
              </div>
            </>
          )}
    </div>
  );
};

export default AIReportPanel;
