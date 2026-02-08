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
}

export const AIReportPanel: React.FC<AIReportPanelProps> = ({
  volumetry,
  patientAge,
  patientSex,
}) => {
  const { t, i18n } = useTranslation();
  const [expanded, setExpanded] = useState(true);
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
    onSuccess: (data) => setReport(data),
  });

  const handleGenerate = () => {
    const findings: Record<string, any> = {};
    if (indication) findings.clinical_indication = indication;
    if (technique) findings.technique = technique;
    if (observations) findings.additional_observations = observations;
    if (patientAge) findings.patient_age = patientAge;
    if (patientSex) findings.patient_sex = patientSex;

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
    stroke: 'M13 10V3L4 14h7v7l9-11h-7z',
    tumor: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z',
    dementia: 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z',
  };

  return (
    <div className="bg-gray-800 rounded-lg shadow-lg">
      {/* Header */}
      <div
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-gray-700 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          {t('report.title', 'AI Report')}
        </h3>
        <span className="text-gray-400 text-sm">{expanded ? '\u25BC' : '\u25B6'}</span>
      </div>

      {expanded && (
        <div className="p-3 space-y-3 border-t border-gray-700">
          {/* Report not yet generated */}
          {!report && (
            <>
              {/* Template selection */}
              <div>
                <label className="block text-xs text-gray-300 mb-1">
                  {t('report.template', 'Template')}
                </label>
                <div className="grid grid-cols-2 gap-1">
                  {(templates ?? [
                    { id: 'general', name: 'General', description: '' },
                    { id: 'stroke', name: 'Stroke', description: '' },
                    { id: 'tumor', name: 'Tumor', description: '' },
                    { id: 'dementia', name: 'Dementia', description: '' },
                  ] as ReportTemplateInfo[]).map((tmpl) => (
                    <button
                      key={tmpl.id}
                      onClick={() => setTemplate(tmpl.id)}
                      className={`px-2 py-2 rounded text-xs font-medium transition-colors flex items-center gap-1.5 ${
                        template === tmpl.id
                          ? 'bg-amber-600 text-white'
                          : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
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
                <label className="block text-xs text-gray-300 mb-1">
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
                          ? 'bg-amber-600 text-white'
                          : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                      }`}
                    >
                      {lang.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Clinical indication */}
              <div>
                <label className="block text-xs text-gray-300 mb-1">
                  {t('report.indication', 'Clinical Indication')}
                </label>
                <input
                  type="text"
                  value={indication}
                  onChange={(e) => setIndication(e.target.value)}
                  placeholder={t('report.indicationPlaceholder', 'e.g., Headache, rule out mass')}
                  className="w-full px-2 py-1.5 bg-gray-700 border border-gray-600 rounded text-xs text-white placeholder-gray-500 focus:outline-none focus:border-amber-500"
                />
              </div>

              {/* Technique */}
              <div>
                <label className="block text-xs text-gray-300 mb-1">
                  {t('report.technique', 'Technique/Sequences')}
                </label>
                <input
                  type="text"
                  value={technique}
                  onChange={(e) => setTechnique(e.target.value)}
                  placeholder={t('report.techniquePlaceholder', 'e.g., T1, T2, FLAIR, DWI, Gd+')}
                  className="w-full px-2 py-1.5 bg-gray-700 border border-gray-600 rounded text-xs text-white placeholder-gray-500 focus:outline-none focus:border-amber-500"
                />
              </div>

              {/* Additional observations */}
              <div>
                <label className="block text-xs text-gray-300 mb-1">
                  {t('report.observations', 'Additional Observations')}
                </label>
                <textarea
                  value={observations}
                  onChange={(e) => setObservations(e.target.value)}
                  placeholder={t('report.observationsPlaceholder', 'Any additional findings or context...')}
                  rows={2}
                  className="w-full px-2 py-1.5 bg-gray-700 border border-gray-600 rounded text-xs text-white placeholder-gray-500 focus:outline-none focus:border-amber-500 resize-none"
                />
              </div>

              {/* Volumetry indicator */}
              {volumetry && (
                <div className="flex items-center gap-1.5 px-2 py-1.5 bg-purple-900/30 border border-purple-800 rounded">
                  <svg className="w-3.5 h-3.5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  <span className="text-xs text-purple-300">
                    {t('report.volumetryIncluded', 'Volumetry data will be included')}
                  </span>
                </div>
              )}

              {/* Error */}
              {generateMutation.isError && (
                <div className="p-2 bg-red-900/30 border border-red-800 rounded text-xs text-red-300">
                  {(generateMutation.error as Error)?.message || t('report.generateError', 'Report generation failed')}
                </div>
              )}

              {/* Generate button */}
              <button
                onClick={handleGenerate}
                disabled={generateMutation.isPending}
                className="w-full px-3 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded text-sm font-medium transition-colors flex items-center justify-center gap-2"
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

          {/* Report generated — show result */}
          {report && (
            <>
              {/* Report header info */}
              <div className="flex items-center justify-between text-xs text-gray-400">
                <span>
                  {report.template_type.charAt(0).toUpperCase() + report.template_type.slice(1)} | {report.language.toUpperCase()}
                </span>
                <span>{report.processing_time_ms}ms</span>
              </div>

              {/* Report content */}
              <div className="bg-gray-900 rounded p-3 max-h-80 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-600 scrollbar-track-gray-900">
                <pre className="text-xs text-gray-200 whitespace-pre-wrap font-mono leading-relaxed">
                  {report.content}
                </pre>
              </div>

              {/* Token usage */}
              {report.tokens_used && (
                <p className="text-xs text-gray-500 text-right">
                  {t('report.tokens', 'Tokens')}: {report.tokens_used.input} in / {report.tokens_used.output} out
                </p>
              )}

              {/* Action buttons */}
              <div className="flex gap-2">
                <button
                  onClick={handleCopy}
                  className="flex-1 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-xs transition-colors flex items-center justify-center gap-1"
                >
                  {copied ? (
                    <>
                      <svg className="w-3.5 h-3.5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
                  className="flex-1 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-xs transition-colors"
                >
                  {t('report.newReport', 'New Report')}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default AIReportPanel;
