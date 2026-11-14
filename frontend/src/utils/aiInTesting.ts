/**
 * RC-130 (REQ-SAFE-060; HAZ-003, HAZ-017) — DRAFT, PENDING owner approval.
 *
 * Research stage (owner decision 2026-11-13): the AI comments of the verified report run with a model MSTool-AI has
 * not yet validated in its registered study. ONE place decides whether a model wrote text in a draft, words the
 * in-testing notice in the REPORT's language (not the interface's: a printed German report must carry the German
 * notice), and builds the text the Copy buttons put on the clipboard (the notice first), so the viewer, the panel and
 * the clipboard can never disagree.
 */
import i18n from '@/i18n/config';
import type { ReportResponse } from '@/types/ai';

type ReportLike = Pick<ReportResponse, 'content' | 'language' | 'model' | 'verification'>;

/** A model wrote text in this draft: the rule that names the model in the viewer's footer (third review of PR #78,
 *  item 4). With a verification record, only when its checked comments are in the draft; a report from before the
 *  verified flow (no record) that names a model was written by that model. */
export function modelWroteText(report: ReportLike): boolean {
  const verification = report.verification ?? null;
  return Boolean(report.model) && (verification ? verification.interpretive_text === 'delivered' : true);
}

/** The in-testing notice in the report's language, or null when no model wrote text in the draft. */
export function aiInTestingNotice(report: ReportLike): string | null {
  if (!modelWroteText(report)) return null;
  const lng = report.language || i18n.language;
  return i18n.getFixedT(lng)('reportViewer.aiInTesting', { model: report.model });
}

/** What the Copy buttons put on the clipboard: the notice first whenever a model wrote text in the draft. */
export function textToCopy(report: ReportLike): string {
  const notice = aiInTestingNotice(report);
  return notice ? `${notice}\n\n${report.content}` : report.content;
}
