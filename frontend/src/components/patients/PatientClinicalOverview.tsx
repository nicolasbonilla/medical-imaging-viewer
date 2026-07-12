import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { Brain, CalendarClock, Activity, Layers, type LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { StudySummary } from '@/types/ehr';
import { formatDate } from '@/utils/formatDate';

interface PatientClinicalOverviewProps {
  /** Studies loaded for this patient (current page). */
  studies: StudySummary[];
  /** Authoritative total study count (may exceed the loaded page). */
  totalStudies: number;
}

interface Tile {
  key: string;
  label: string;
  value: string;
  context: string;
  icon: LucideIcon;
  accent: string;
  chipBg: string;
}

const MS_PER_DAY = 1000 * 60 * 60 * 24;

function formatBytes(bytes: number): string {
  if (!bytes) return '0 MB';
  const mb = bytes / (1024 * 1024);
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb.toFixed(mb < 10 ? 1 : 0)} MB`;
}

/**
 * At-a-glance imaging summary for a patient — the "clinical intelligence" band
 * on the patient detail page. Every value is a REAL aggregate derived from the
 * patient's own studies (no fabricated metrics). The monitoring-window tile is
 * the core MS-follow-up signal: how long this patient has been tracked and how
 * many scans span that window. Premium entry-surface register, dark clinical
 * palette per DESIGN_SYSTEM.md.
 */
export function PatientClinicalOverview({ studies, totalStudies }: PatientClinicalOverviewProps) {
  const { t } = useTranslation();

  const tiles = useMemo<Tile[]>(() => {
    const dates = studies
      .map((s) => new Date(s.study_date).getTime())
      .filter((n) => !Number.isNaN(n))
      .sort((a, b) => a - b);
    const first = dates[0];
    const latest = dates[dates.length - 1];
    const spanDays = first && latest ? Math.round((latest - first) / MS_PER_DAY) : 0;

    // Monitoring window — the MS longitudinal signal.
    let windowValue: string;
    let windowContext: string;
    if (dates.length <= 1) {
      windowValue = t('patients.clinical.baseline', 'Baseline');
      windowContext = t('patients.clinical.baselineHint', 'single study on record');
    } else if (spanDays >= 365) {
      const years = spanDays / 365;
      windowValue = `${years.toFixed(1)} ${t('patients.clinical.years', 'yr')}`;
      windowContext = t('patients.clinical.acrossScans', '{{count}} scans tracked', { count: dates.length });
    } else if (spanDays >= 30) {
      windowValue = `${Math.round(spanDays / 30.44)} ${t('patients.clinical.months', 'mo')}`;
      windowContext = t('patients.clinical.acrossScans', '{{count}} scans tracked', { count: dates.length });
    } else {
      windowValue = `${spanDays} ${t('patients.clinical.days', 'days')}`;
      windowContext = t('patients.clinical.acrossScans', '{{count}} scans tracked', { count: dates.length });
    }

    const modalities = Array.from(new Set(studies.map((s) => s.modality))).filter(Boolean);
    const images = studies.reduce((sum, s) => sum + (s.instance_count || 0), 0);
    const bytes = studies.reduce((sum, s) => sum + (s.total_size_bytes || 0), 0);

    return [
      {
        key: 'studies',
        label: t('patients.clinical.studies', 'Imaging Studies'),
        value: String(totalStudies),
        context: modalities.length
          ? modalities.join(' · ')
          : t('patients.clinical.noModality', 'no modality'),
        icon: Brain, accent: '#A78BFA', chipBg: 'rgba(139,92,246,0.12)',
      },
      {
        key: 'window',
        label: t('patients.clinical.monitoring', 'Monitoring Window'),
        value: windowValue,
        context: windowContext,
        icon: CalendarClock, accent: '#60A5FA', chipBg: 'rgba(59,130,246,0.12)',
      },
      {
        key: 'latest',
        label: t('patients.clinical.latestScan', 'Latest Scan'),
        value: latest ? formatDate(latest) : '—',
        context: t('patients.clinical.mostRecent', 'most recent study'),
        icon: Activity, accent: '#34D399', chipBg: 'rgba(16,185,129,0.12)',
      },
      {
        key: 'volume',
        label: t('patients.clinical.imagingData', 'Imaging Data'),
        value: images ? images.toLocaleString() : '—',
        context: images
          ? `${t('patients.clinical.images', 'images')} · ${formatBytes(bytes)}`
          : t('patients.clinical.noImages', 'no images uploaded'),
        icon: Layers, accent: '#38BDF8', chipBg: 'rgba(14,165,233,0.12)',
      },
    ];
  }, [studies, totalStudies, t]);

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4" style={{ gap: 12 }}>
      {tiles.map((tile, i) => {
        const Icon = tile.icon;
        return (
          <motion.div
            key={tile.key}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: i * 0.06, ease: [0.2, 0, 0, 1] }}
            className="relative overflow-hidden border border-gray-800"
            style={{ background: '#111827', borderRadius: 12, padding: 16 }}
          >
            <span
              aria-hidden
              className="absolute left-0 top-0 h-[2px] w-full"
              style={{ background: `linear-gradient(90deg, ${tile.accent}, transparent 70%)`, opacity: 0.7 }}
            />
            <div className="flex items-start justify-between" style={{ marginBottom: 10 }}>
              <span
                className="inline-flex items-center justify-center"
                style={{ width: 34, height: 34, borderRadius: 9, background: tile.chipBg }}
              >
                <Icon style={{ width: 18, height: 18, color: tile.accent }} aria-hidden />
              </span>
            </div>
            <div style={{ fontSize: 22, fontWeight: 700, lineHeight: 1.1, color: '#F9FAFB', letterSpacing: '-0.01em' }}>
              {tile.value}
            </div>
            <div
              style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.05em', color: '#9CA3AF', textTransform: 'uppercase', marginTop: 8 }}
            >
              {tile.label}
            </div>
            <div style={{ fontSize: 11, color: '#6B7280', marginTop: 2 }}>{tile.context}</div>
          </motion.div>
        );
      })}
    </div>
  );
}
