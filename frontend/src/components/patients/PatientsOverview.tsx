import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { Users, Activity, Brain, FileText, type LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface PatientLike {
  status?: string;
  study_count?: number | null;
  document_count?: number | null;
}

interface PatientsOverviewProps {
  patients: PatientLike[];
  total: number;
}

interface Tile {
  key: string;
  label: string;
  value: number;
  context: string;
  icon: LucideIcon;
  accent: string;     // icon + number accent
  chipBg: string;     // icon chip background
}

/**
 * Cohort overview KPIs for the Patients dashboard — a "clinical command center"
 * header row. Values are REAL aggregates derived from the loaded cohort (no
 * fabricated metrics). Premium "entry surface" register per the dual-register
 * design direction: confident stat numbers, generous cards — while staying
 * within the dark clinical palette of DESIGN_SYSTEM.md.
 */
export function PatientsOverview({ patients, total }: PatientsOverviewProps) {
  const { t } = useTranslation();

  const tiles = useMemo<Tile[]>(() => {
    const active = patients.filter((p) => (p.status || '').toLowerCase() === 'active').length;
    const studies = patients.reduce((s, p) => s + (p.study_count || 0), 0);
    const documents = patients.reduce((s, p) => s + (p.document_count || 0), 0);
    return [
      {
        key: 'patients', label: t('patients.overview.total', 'Patients'),
        value: total, context: t('patients.overview.inRegistry', 'in registry'),
        icon: Users, accent: '#60A5FA', chipBg: 'rgba(59,130,246,0.12)',
      },
      {
        key: 'active', label: t('patients.overview.active', 'Active'),
        value: active, context: t('patients.overview.underCare', 'under active care'),
        icon: Activity, accent: '#34D399', chipBg: 'rgba(16,185,129,0.12)',
      },
      {
        key: 'studies', label: t('patients.overview.studies', 'MRI Studies'),
        value: studies, context: t('patients.overview.aiReady', 'AI-analysis ready'),
        icon: Brain, accent: '#A78BFA', chipBg: 'rgba(139,92,246,0.12)',
      },
      {
        key: 'documents', label: t('patients.overview.documents', 'Documents'),
        value: documents, context: t('patients.overview.onFile', 'clinical records'),
        icon: FileText, accent: '#38BDF8', chipBg: 'rgba(14,165,233,0.12)',
      },
    ];
  }, [patients, total, t]);

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
            {/* hairline accent along the top edge */}
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
            <div style={{ fontSize: 26, fontWeight: 700, lineHeight: 1, color: '#F9FAFB', letterSpacing: '-0.01em' }}>
              {tile.value.toLocaleString()}
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
