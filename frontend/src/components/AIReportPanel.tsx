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

import React, { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { aiReportAPI } from '@/api/aiReport';
import { segmentationAPI } from '@/api/segmentation';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { Button, Input } from '@/components/ui';
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

/** Shared styles (design-system v2 tokens). */
const FIELD_LABEL = 'mb-1.5 block text-xs font-medium text-ink-muted';
const FOCUS_RING = 'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60';
/** Segmented option buttons (template / language): tinted brand selection, neutral otherwise. */
const OPTION_BASE = `rounded-lg border text-xs font-medium transition-colors ${FOCUS_RING}`;
const OPTION_ON = 'border-brand-500/30 bg-brand-950 text-brand-400';
const OPTION_OFF = 'border-surface-border bg-surface-raised text-ink-soft hover:bg-surface-hover hover:text-ink-base';

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
  // Element ids that tie each visible label to its control (a11y only).
  const templateLabelId = useId();
  const languageLabelId = useId();
  const observationsId = useId();

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
                <span id={templateLabelId} className={FIELD_LABEL}>
                  {t('report.template', 'Template')}
                </span>
                <div className="grid grid-cols-2 gap-1.5" role="group" aria-labelledby={templateLabelId}>
                  {(templates ?? [
                    { id: 'general', name: t('report.templates.general', 'General'), description: '' },
                    { id: 'ms_activity', name: t('report.templates.ms_activity', 'MS Activity'), description: '' },
                    { id: 'ms_lesion_burden', name: t('report.templates.ms_lesion_burden', 'Lesion Burden'), description: '' },
                  ] as ReportTemplateInfo[]).map((tmpl) => (
                    <button
                      key={tmpl.id}
                      type="button"
                      aria-pressed={template === tmpl.id}
                      onClick={() => setTemplate(tmpl.id)}
                      className={`${OPTION_BASE} flex min-h-8 items-center gap-1.5 px-2 py-1.5 text-left ${
                        template === tmpl.id ? OPTION_ON : OPTION_OFF
                      }`}
                      title={tmpl.description}
                    >
                      <svg className="h-3.5 w-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={templateIcons[tmpl.id] || templateIcons.general} />
                      </svg>
                      <span className="truncate">{tmpl.name}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Language selection */}
              <div>
                <span id={languageLabelId} className={FIELD_LABEL}>
                  {t('report.language', 'Language')}
                </span>
                <div className="flex gap-1.5" role="group" aria-labelledby={languageLabelId}>
                  {[
                    { code: 'en', label: 'EN' },
                    { code: 'es', label: 'ES' },
                    { code: 'de', label: 'DE' },
                  ].map((lang) => (
                    <button
                      key={lang.code}
                      type="button"
                      aria-pressed={language === lang.code}
                      onClick={() => setLanguage(lang.code)}
                      className={`${OPTION_BASE} h-8 flex-1 px-2 ${
                        language === lang.code ? OPTION_ON : OPTION_OFF
                      }`}
                    >
                      {lang.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Clinical indication */}
              <Input
                label={t('report.indication', 'Clinical Indication')}
                type="text"
                value={indication}
                onChange={(e) => setIndication(e.target.value)}
                placeholder={t('report.indicationPlaceholder', 'e.g., Headache, rule out mass')}
                className="h-8 text-xs"
              />

              {/* Technique */}
              <Input
                label={t('report.technique', 'Technique/Sequences')}
                type="text"
                value={technique}
                onChange={(e) => setTechnique(e.target.value)}
                placeholder={t('report.techniquePlaceholder', 'e.g., T1, T2, FLAIR, DWI, Gd+')}
                className="h-8 text-xs"
              />

              {/* Additional observations */}
              <div>
                <label htmlFor={observationsId} className={FIELD_LABEL}>
                  {t('report.observations', 'Additional Observations')}
                </label>
                <textarea
                  id={observationsId}
                  value={observations}
                  onChange={(e) => setObservations(e.target.value)}
                  placeholder={t('report.observationsPlaceholder', 'Any additional findings or context...')}
                  rows={2}
                  className={`w-full resize-none rounded-lg border border-surface-border bg-surface-base px-3 py-2 text-xs text-ink-base placeholder-ink-faint transition-colors hover:border-surface-hover ${FOCUS_RING}`}
                />
              </div>

              {/* Active segmentation indicator — lesion data will be auto-collected */}
              {useSegmentationStore.getState().currentSegmentation && (
                <div className="flex items-center gap-1.5 rounded-lg border border-clinical-info/30 bg-clinical-info/10 px-2.5 py-2">
                  <svg className="h-3.5 w-3.5 shrink-0 text-clinical-info" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                  </svg>
                  <span className="text-xs text-clinical-info">
                    {t('report.lesionDataIncluded', 'Lesion analysis data will be auto-collected')}
                  </span>
                </div>
              )}

              {/* Volumetry indicator */}
              {volumetry && (
                <div className="flex items-center gap-1.5 rounded-lg border border-clinical-info/30 bg-clinical-info/10 px-2.5 py-2">
                  <svg className="h-3.5 w-3.5 shrink-0 text-clinical-info" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  <span className="text-xs text-clinical-info">
                    {t('report.volumetryIncluded', 'Volumetry data will be included')}
                  </span>
                </div>
              )}

              {/* Error */}
              {generateMutation.isError && (
                <div className="rounded-lg border border-clinical-crit/30 bg-clinical-crit/10 px-2.5 py-2 text-xs leading-snug text-clinical-crit">
                  {/* CAPA-008: a 422 means no measurement was available — say so instead of a generic error. */}
                  {(generateMutation.error as any)?.response?.status === 422
                    ? t('report.noMeasurements', 'No measurements are available for this study. Open a segmentation and run its analysis first: a report without measurements would be invented.')
                    : (generateMutation.error as Error)?.message || t('report.generateError', 'Report generation failed')}
                </div>
              )}

              {/* Generate button */}
              <Button
                variant="primary"
                size="md"
                fullWidth
                onClick={handleGenerate}
                disabled={generateMutation.isPending}
                aria-busy={generateMutation.isPending || undefined}
              >
                {generateMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    <span>{t('report.generating', 'Generating...')}</span>
                  </>
                ) : (
                  <>
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <span>{t('report.generate', 'Generate Report')}</span>
                  </>
                )}
              </Button>
            </>
          )}

          {/* Report generated — compact summary */}
          {report && (
            <>
              {/* Success indicator */}
              <div className="rounded-lg border border-clinical-good/30 bg-clinical-good/10 p-3 text-center">
                <svg className="mx-auto mb-1.5 h-6 w-6 text-clinical-good" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <p className="text-sm font-medium text-clinical-good">
                  {t('reportViewer.reportReady', 'Report generated successfully')}
                </p>
                <p className="mt-1 text-xs tabular-nums text-ink-muted">
                  {report.template_type.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')} | {report.language.toUpperCase()} | {report.processing_time_ms}ms
                </p>
              </div>

              {/* Action buttons */}
              <div className="space-y-1.5">
                <Button
                  variant="primary"
                  size="md"
                  fullWidth
                  onClick={() => onReportGenerated?.(report)}
                  leftIcon={
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  }
                >
                  {t('reportViewer.viewFullReport', 'View Full Report')}
                </Button>
                <div className="flex gap-1.5">
                  <Button
                    variant="secondary"
                    size="sm"
                    className="flex-1 gap-1"
                    onClick={handleCopy}
                  >
                    {copied ? (
                      <>
                        <svg className="h-3.5 w-3.5 text-clinical-good" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                        {t('report.copied', 'Copied!')}
                      </>
                    ) : (
                      <>
                        <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                        </svg>
                        {t('report.copy', 'Copy')}
                      </>
                    )}
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    className="flex-1"
                    onClick={handleReset}
                  >
                    {t('report.newReport', 'New Report')}
                  </Button>
                </div>
              </div>
            </>
          )}
    </div>
  );
};

export default AIReportPanel;
