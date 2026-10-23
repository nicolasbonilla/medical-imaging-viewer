/**
 * SliceThicknessReliabilityCard — "reliability by slice thickness" next to the lesion results.
 *
 * CP-SLICE-THICKNESS-001 — DRAFT, PENDING owner approval. Reachable only through the feature
 * flag VITE_ENABLE_SLICE_THICKNESS_RELIABILITY (OFF by default, RC-058), loaded lazily.
 * Research input: Paper A v0.3 (PR #54), `docs/research/paper/APP-FEATURE-slice-thickness-reliability.md`.
 *
 * Shows, for the image the segmentation was drawn on:
 *  - the acquisition slice thickness and how it is known (RC-054/RC-055): from a DICOM header,
 *    as a lower bound from the image grid ("at least"), or "not determinable" with the reason
 *    — never the legacy `slice_thickness` field and never a default;
 *  - the thickness band, and from which lesion size research data found lesions 8 times in 10
 *    and half of the time, worst case over the band's evidence rows (RC-057), with the evidence
 *    size and the source record of every number (pre-registered bands only; post-hoc evidence
 *    is refused by the asset check);
 *  - plain guidance: an empty or short list does not mean no lesions; on thick or unknown
 *    thickness, a 3D FLAIR is recommended for small lesions;
 *  - NO false-lesion rate, at any thickness (RC-056).
 *
 * No new endpoint: geometry comes with the image the viewer already loaded, or from the
 * existing authorized `/imaging/metadata` route for another image of the same study.
 *
 * @module components/SliceThicknessReliabilityCard
 */
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Layers, AlertTriangle } from 'lucide-react';
import { imagingAPI } from '@/api/imaging';
import { useViewerStore } from '@/store/useViewerStore';
import {
  ASSET,
  assessReliability,
  fill,
  locateSource,
  parseGeometry,
  pickLang,
  resolveThickness,
  type Lang,
  type ParsedGeometry,
  type ReliabilityView,
  type StudyInstanceLike,
} from '@/utils/sliceThicknessReliability';

interface Props {
  /** Storage key (`file_id`) of the image the segmentation was drawn on. */
  sourceFileId?: string;
  /** Instances of the current study (to find the original FLAIR of a processed image). */
  studyInstances?: ReadonlyArray<StudyInstanceLike>;
}

type Messages = Record<string, string> & { reasons: Record<string, string> };

async function fetchGeometry(fileId: string): Promise<ParsedGeometry> {
  try {
    const data = await imagingAPI.getMetadata(fileId);
    return parseGeometry(data?.metadata?.acquisition_geometry);
  } catch {
    return { state: 'not_determinable', mm: null, reason: 'unreadable' };
  }
}

const LOCALE: Record<Lang, string> = { en: 'en-GB', es: 'es-ES', de: 'de-DE' };

function num(value: number, lang: Lang, digits = 1): string {
  return value.toLocaleString(LOCALE[lang], { maximumFractionDigits: digits });
}

function pct(value: number): string {
  return `${Math.round(value * 100)} %`;
}

export default function SliceThicknessReliabilityCard({ sourceFileId, studyInstances }: Props) {
  const { i18n } = useTranslation();
  const lang = pickLang(i18n?.language);
  const m = ASSET.messages[lang] as unknown as Messages;
  const currentSeries = useViewerStore((s) => s.currentSeries);

  const located = useMemo(() => locateSource(sourceFileId, studyInstances), [sourceFileId, studyInstances]);
  // RC-055: the viewer's loaded image is used only if it IS the segmentation's image.
  const ownFromViewer = !!sourceFileId && currentSeries?.file_id === sourceFileId;
  const originalFileId = located.original.kind === 'found' ? located.original.fileId : undefined;

  const ownQuery = useQuery({
    queryKey: ['acquisition-geometry', sourceFileId],
    queryFn: () => fetchGeometry(sourceFileId as string),
    enabled: !!sourceFileId && !ownFromViewer,
    staleTime: Infinity,
    retry: false,
  });
  const originalQuery = useQuery({
    queryKey: ['acquisition-geometry', originalFileId],
    queryFn: () => fetchGeometry(originalFileId as string),
    enabled: !!originalFileId,
    staleTime: Infinity,
    retry: false,
  });

  let own: ParsedGeometry | undefined;
  if (!sourceFileId) own = { state: 'not_determinable', mm: null, reason: 'no_source_image' };
  else if (ownFromViewer) own = parseGeometry(currentSeries?.metadata?.acquisition_geometry);
  else own = ownQuery.data;
  const loading = !own || (!!originalFileId && !originalQuery.data);

  const view: ReliabilityView | null = useMemo(() => {
    if (loading || !own) return null;
    return assessReliability(
      resolveThickness({
        own,
        ownFilename: located.ownFilename,
        ownIsProcessed: located.ownIsProcessed,
        original: located.original,
        originalGeometry: originalQuery.data ?? null,
      }),
    );
  }, [loading, own, located, originalQuery.data]);

  return (
    <section
      role="note"
      aria-label={m.title}
      data-testid="stc-card"
      className="bg-gray-900/60 rounded-lg p-2.5 border border-sky-800/50 space-y-1.5 text-[10px] leading-snug text-gray-300"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-[11px] font-semibold text-white">
          <Layers className="w-3.5 h-3.5 text-sky-400" aria-hidden="true" />
          {m.title}
        </span>
        <span className="rounded bg-sky-950/70 px-1.5 py-0.5 text-[9px] text-sky-300">{m.badge}</span>
      </div>

      {!view ? (
        <div data-testid="stc-loading" className="text-gray-400">{m.loading}</div>
      ) : (
        <CardBody view={view} m={m} lang={lang} />
      )}
    </section>
  );
}

function CardBody({ view, m, lang }: { view: ReliabilityView; m: Messages; lang: Lang }) {
  const bins = ASSET.size_bins;
  const isBand = view.kind === 'band';

  const thicknessText = (() => {
    if (!isBand || view.mm === null) return m.not_determinable;
    const base = fill(view.basis === 'native' ? m.native : m.at_least, { mm: num(view.mm, lang), file: view.file ?? '' });
    return view.viaOriginal ? `${base} (${fill(m.source_original, { file: view.file ?? '' })})` : base;
  })();

  const bandText = isBand
    ? view.basis === 'at_least'
      ? fill(m.band_at_least, { label: view.bands[0].label[lang] })
      : view.bands.map((b) => b.label[lang]).join(', ')
    : null;

  const sizeFrom = (bin: number | null, withDiameter: boolean, fromKey: string, noneKey: string) =>
    bin === null
      ? m[noneKey]
      : fill(m[fromKey], {
          mm3: num(bins[bin].min_mm3, lang, 0),
          diameter: withDiameter ? `${num(bins[bin].min_diameter_mm, lang)} mm` : '',
        });

  return (
    <>
      <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
        <dt className="text-gray-400">{m.thickness}</dt>
        <dd data-testid="stc-thickness" data-state={view.kind === 'band' ? view.basis : 'not_determinable'} className="text-gray-100">
          {thicknessText}
          {!isBand && (
            <span data-testid="stc-reasons" className="block text-amber-300">
              {view.reasons.map((r) => m.reasons[r] ?? m.reasons.unreadable).join('; ')}
            </span>
          )}
        </dd>
        {isBand && (
          <>
            <dt className="text-gray-400">{m.band}</dt>
            <dd data-testid="stc-band" className="text-gray-100">{bandText}</dd>
            <dt className="text-gray-400">{m.reliable}</dt>
            <dd data-testid="stc-reliable" className="text-gray-100">{sizeFrom(view.reliableBin, true, 'reliable_from', 'reliable_none')}</dd>
            <dt className="text-gray-400">{m.half}</dt>
            <dd data-testid="stc-half" className="text-gray-100">{sizeFrom(view.halfBin, false, 'half_from', 'half_none')}</dd>
          </>
        )}
      </dl>

      {isBand && (
        <div className="overflow-x-auto">
          <table data-testid="stc-table" className="w-full text-[9px]">
            <caption className="text-left text-gray-400 pb-0.5">{m.table_title}</caption>
            <thead>
              <tr className="text-gray-400 border-b border-gray-700">
                <th className="text-left font-normal py-0.5 pr-1" scope="col" />
                {bins.map((b, i) => (
                  <th key={i} scope="col" className="text-right font-normal py-0.5 px-0.5 whitespace-nowrap" title={`${num(b.min_mm3, lang, 0)}${b.max_mm3 ? `-${num(b.max_mm3, lang, 0)}` : '+'} mm³`}>
                    {b.max_diameter_mm === null ? `≥${num(b.min_diameter_mm, lang)}` : `${num(b.min_diameter_mm, lang)}-${num(b.max_diameter_mm, lang)}`} mm
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {view.rows.map((id) => {
                const row = ASSET.evidence_rows[id];
                return (
                  <tr key={id} data-testid={`stc-row-${id}`} className="border-b border-gray-800 align-top">
                    <th scope="row" className="text-left font-normal py-0.5 pr-1 text-gray-300">
                      {row.label[lang]}
                      <span className="block text-gray-500">
                        {fill(m.evidence, { scans: row.scans, patients: row.patients, sites: row.sites })}
                      </span>
                    </th>
                    {row.detection.map((d, i) => (
                      <td key={i} className={`text-right font-mono py-0.5 px-0.5 ${d >= ASSET.reliable_fraction ? 'text-gray-100' : d >= ASSET.half_fraction ? 'text-gray-300' : 'text-amber-300'}`}>
                        {pct(d)}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div data-testid="stc-guidance" className="rounded border border-amber-700/50 bg-amber-900/20 px-2 py-1 text-amber-100 space-y-0.5">
        {!isBand && (
          <p className="flex gap-1">
            <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-px" aria-hidden="true" />
            <span>{m.not_determinable_guidance}</span>
          </p>
        )}
        <p>{m.empty_list}</p>
        {view.thick && <p data-testid="stc-recommend-3d">{m.recommend_3d}</p>}
      </div>

      <div data-testid="stc-false-lesion" className="text-gray-300">
        <span className="font-medium text-gray-100">{m.false_lesion}</span>{' '}
        {view.falseLesionFigure.reason === 'thick_or_unknown' ? m.false_lesion_thick : m.false_lesion_thin}
      </div>

      <p className="text-gray-500">{m.scope}</p>
      <p data-testid="stc-provenance" className="text-gray-600">
        {fill(m.provenance, {
          version: `v${ASSET.asset_version}`,
          commit: `PR #${ASSET.source.pull_request} ${ASSET.source.commit.slice(0, 7)}`,
          records: ASSET.source.records.map((r) => r.path.split('/').pop()).join(', '),
        })}
      </p>
    </>
  );
}
