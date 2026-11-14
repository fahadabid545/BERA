"""Requirement evaluation: judging one CV against each requirement of its project.

One AI call per CV covers every requirement that needs judging. For each the AI gives a verdict
(met, partly met, missing), a short quote and a confidence. The CV text is the guarded text
(see fairness.py), and a quote is only accepted if it really is in that text:

- a quote that is not in the text (or is too long) is discarded and that requirement is asked
  again, once (`ai.invalid_answer_retries`); if it is still wrong the requirement is Missing;
- a met or partly met verdict with no quote at all is Missing (no evidence, no credit);
- a missing verdict carries no quote.

An answer that cannot be used at all (not JSON, wrong shape) is asked for once more, then the
CV fails with a reason. Results are kept per candidate and requirement, so a retry or a
re-scoring only judges what is new or edited. Nothing from the CV or the answer is logged.
"""

import json
import logging
import unicodedata
from dataclasses import dataclass

from django.db import transaction

from ai.client import call_ai
from ai.prompt_versions import SCORING, prompt_text
from core.errors import AppError
from plans.limits import check_ai_allowed
from platform_settings.service import get_setting
from projects.models import Requirement
from projects.requirements import require_requirements_for_scoring

from .models import RequirementResult
from .processing import PermanentFailure, StepContext, register_step

logger = logging.getLogger(__name__)

VERDICTS = set(RequirementResult.Verdict.values)
CONFIDENCES = set(RequirementResult.Confidence.values)
MISSING, LOW = RequirementResult.Verdict.MISSING, RequirementResult.Confidence.LOW

UNUSABLE_REASON = "We could not judge this CV against the requirements. You can retry it."
AI_PAUSED_REASON = "AI scoring is paused for this period. You can retry it later."


class UnusableAnswer(Exception):
    """The answer is not JSON of the expected shape at all."""


@dataclass(frozen=True)
class Judgement:
    verdict: str
    evidence: str
    confidence: str


def _plain(text):
    """Text as it is compared: one Unicode form, no case, single spaces."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _judgement(entry, cv_plain):
    """The checked judgement for one entry of the answer, or None when it must be discarded."""
    verdict, confidence = entry.get("verdict"), entry.get("confidence")
    if verdict not in VERDICTS or confidence not in CONFIDENCES:
        return None
    if verdict == MISSING:
        return Judgement(MISSING, "", confidence)  # nothing is quoted for something missing
    quote = entry.get("evidence")
    if not isinstance(quote, str):
        return None
    quote = " ".join(quote.split())
    if not quote:
        return Judgement(MISSING, "", confidence)  # no evidence means missing
    if len(quote) > get_setting("evaluation.evidence_max_length") or _plain(quote) not in cv_plain:
        return None  # an invented, altered or overlong quote
    return Judgement(verdict, quote, confidence)


def check_answer(raw_text, wanted, cv_text):
    """{number: Judgement} for the wanted requirement numbers whose entry is valid. Entries that
    are invalid, repeated or about another number are left out. Raises `UnusableAnswer`."""
    try:
        answer = json.loads(raw_text)
    except (TypeError, ValueError) as error:
        raise UnusableAnswer("not json") from error
    entries = answer.get("results") if isinstance(answer, dict) else None
    if not isinstance(entries, list):
        raise UnusableAnswer("shape")
    cv_plain, found = _plain(cv_text), {}
    for entry in entries:
        number = entry.get("requirement") if isinstance(entry, dict) else None
        if isinstance(number, bool) or number not in wanted or number in found:
            continue
        if (judgement := _judgement(entry, cv_plain)) is not None:
            found[number] = judgement
    return found


def _question(wanted, cv_text):
    lines = "\n".join(f"{number}. {text}" for number, text in wanted.items())
    return f"Requirements:\n{lines}\n\nCV:\n{cv_text}"


def judge(cv_file, requirements, cv_text):
    """{requirement: Judgement} for the given requirements, asking the AI (once, plus the retry)."""
    project = cv_file.project
    by_number = {position: requirement for position, requirement in enumerate(requirements, 1)}
    pending = {number: requirement.text for number, requirement in by_number.items()}
    judged, understood = {}, False
    for _ in range(1 + get_setting("ai.invalid_answer_retries")):
        answer = call_ai(
            cv_file.company_id,
            model=project.scoring_model,
            instructions=prompt_text(SCORING, project.scoring_prompt_version),
            text=_question(pending, cv_text),
            project_id=project.pk,
            cv_id=cv_file.pk,
            max_output_tokens=get_setting("ai.evaluation_max_output_tokens"),
        )
        try:
            found = check_answer(answer.text, set(pending), cv_text)
        except UnusableAnswer:
            logger.warning("The AI gave a requirement evaluation that could not be used.")
            continue
        understood = True
        judged.update(found)
        pending = {number: text for number, text in pending.items() if number not in found}
        if not pending:
            break
    if not understood:
        raise PermanentFailure(UNUSABLE_REASON)
    for number in pending:  # still wrong after the retry: no evidence, so missing
        judged[number] = Judgement(MISSING, "", LOW)
    return {by_number[number]: judgement for number, judgement in judged.items()}


def _needing_judgement(candidate, requirements):
    """The requirements with no result yet, or whose text changed since they were judged."""
    done = {
        result.requirement_id: result.requirement_text
        for result in RequirementResult.objects.filter(candidate=candidate)
    }
    return [req for req in requirements if done.get(req.pk) != req.text]


def evaluate_candidate(candidate, cv_text):
    """Judges the candidate's CV against the project's requirements and saves the results."""
    project = candidate.project
    try:
        require_requirements_for_scoring(project)
    except AppError as error:
        raise PermanentFailure(error.message) from error
    requirements = list(Requirement.objects.filter(project=project).order_by("position"))
    needed = _needing_judgement(candidate, requirements)
    if not needed:
        return
    if not check_ai_allowed(candidate.company_id).allowed:
        raise PermanentFailure(AI_PAUSED_REASON)
    judged = judge(candidate.cv_file, needed, cv_text)
    with transaction.atomic():
        for requirement, judgement in judged.items():
            RequirementResult.objects.update_or_create(
                candidate=candidate,
                requirement=requirement,
                defaults={
                    "company_id": candidate.company_id,
                    "requirement_text": requirement.text,
                    "verdict": judgement.verdict,
                    "evidence": judgement.evidence,
                    "confidence": judgement.confidence,
                    "model": project.scoring_model,
                    "prompt_version": project.scoring_prompt_version,
                },
            )


def evaluate_the_requirements(context: StepContext):
    """Slot `requirement_evaluation`: judges the guarded CV text, never the original."""
    evaluate_candidate(context.cv_file.candidate, context.state["scoring_text"])


register_step("requirement_evaluation", evaluate_the_requirements)
