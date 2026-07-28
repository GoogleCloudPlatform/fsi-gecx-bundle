from __future__ import annotations

import re


_CONFIRMATION_PROMPT_PATTERN = re.compile(
    r"\b(?:confirm|is that (?:right|correct)|does that sound right|did i get that right|"
    r"are you disputing|you (?:do not|don't) recognize)\b",
    re.IGNORECASE,
)
_SUMMARY_TRANSACTION_PATTERN = re.compile(
    r"\$([\d,]+)\.(\d{2})\s+at\s+(.+?)(?=,\s+\$| on card ending)",
    re.IGNORECASE,
)
_CARD_SUFFIX_PATTERN = re.compile(r"card ending\s+(\d{4})", re.IGNORECASE)
_DIGIT_WORDS = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}
_SMALL_NUMBER_WORDS = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
_TENS_WORDS = (
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
)


def _normalized_spoken_text(value):
    return " ".join(re.sub(r"[^a-z0-9$.,]+", " ", (value or "").lower()).split())


def _integer_words(value):
    if value < 20:
        return _SMALL_NUMBER_WORDS[value]
    if value < 100:
        tens, remainder = divmod(value, 10)
        return " ".join(
            part
            for part in (
                _TENS_WORDS[tens],
                _integer_words(remainder) if remainder else "",
            )
            if part
        )
    if value < 1000:
        hundreds, remainder = divmod(value, 100)
        return " ".join(
            part
            for part in (
                f"{_SMALL_NUMBER_WORDS[hundreds]} hundred",
                _integer_words(remainder) if remainder else "",
            )
            if part
        )
    if value < 1_000_000:
        thousands, remainder = divmod(value, 1000)
        return " ".join(
            part
            for part in (
                f"{_integer_words(thousands)} thousand",
                _integer_words(remainder) if remainder else "",
            )
            if part
        )
    return str(value)


def _amount_is_present(transcript, dollars, cents):
    numeric = re.compile(
        rf"(?:\$\s*{dollars:,}(?:\.{cents:02d})?"
        rf"|\b{dollars:,}(?:\.{cents:02d})?\s+(?:us\s+)?dollars?\b)",
        re.IGNORECASE,
    )
    if numeric.search(transcript):
        return True
    spoken = f"{_integer_words(dollars)} dollar"
    spoken_variants = (spoken, f"{spoken}s")
    if cents:
        spoken_variants = tuple(
            f"{variant} and {_integer_words(cents)} cents"
            for variant in spoken_variants
        )
    normalized = _normalized_spoken_text(transcript)
    return any(variant in normalized for variant in spoken_variants)


def _presentation_matches(summary, transcript):
    if not str(summary or "").strip() or not _CONFIRMATION_PROMPT_PATTERN.search(
        transcript or ""
    ):
        return False
    normalized_summary = _normalized_spoken_text(summary)
    normalized_output = _normalized_spoken_text(transcript)
    transactions = _SUMMARY_TRANSACTION_PATTERN.findall(summary)
    has_material_facts = bool(transactions)
    for dollars_text, cents_text, merchant in transactions:
        if not _amount_is_present(
            transcript,
            int(dollars_text.replace(",", "")),
            int(cents_text),
        ):
            return False
        if _normalized_spoken_text(merchant) not in normalized_output:
            return False
    suffix_match = _CARD_SUFFIX_PATTERN.search(summary)
    if suffix_match:
        has_material_facts = True
        suffix = suffix_match.group(1)
        spoken_suffix = " ".join(_DIGIT_WORDS[digit] for digit in suffix)
        if suffix not in normalized_output and spoken_suffix not in normalized_output:
            return False
    if "want to dispute" in normalized_summary and "disput" not in normalized_output:
        return False
    if "block the current card" in normalized_summary:
        has_material_facts = True
        if not any(
            word in normalized_output for word in ("block", "cancel", "deactivate")
        ):
            return False
    if "issue a replacement" in normalized_summary:
        has_material_facts = True
        if (
            "replacement" not in normalized_output
            and "new card" not in normalized_output
        ):
            return False
    if "request specialist review" in normalized_summary:
        has_material_facts = True
        if "specialist" not in normalized_output:
            return False
    if "recognize all reviewed activity" in normalized_summary:
        has_material_facts = True
        if "recognize" not in normalized_output or "all" not in normalized_output:
            return False
        if not (
            (
                "no fraud dispute" in normalized_output
                or "not dispute" in normalized_output
            )
            and (
                "no replacement" in normalized_output
                or "not replace" in normalized_output
            )
        ):
            return False
    return has_material_facts


def after_model_callback(callback_context, llm_response):
    """Record proposal presentation evidence without replacing native audio."""
    if llm_response.partial is True:
        return None
    if not callback_context.variables.get("proposal_id"):
        return None
    if callback_context.variables.get("proposal_presentation_turn_id"):
        return None

    content = llm_response.content
    parts = content.parts if content and content.parts else []
    output = " ".join(str(part.text_or_transcript() or "") for part in parts).strip()
    invocation_id = str(callback_context.invocation_id or "")
    if not output or not invocation_id:
        return None
    if not _presentation_matches(
        callback_context.variables.get("proposal_customer_safe_summary"),
        output,
    ):
        return None

    callback_context.variables["proposal_presentation_turn_id"] = invocation_id
    return None
