"""
Day 14 — AI Evaluation & Benchmarking Pipeline
AICB-P1: AI Practical Competency Program, Phase 1

Key concepts from lecture:
    - Evaluation = Scientific Method for AI (Hypothesis → Experiment → Measure → Conclude → Iterate)
    - 4 nhóm metrics: Task Completion, Answer Quality, RAG-Specific, Business
    - RAG pipeline metrics: Context Recall → Context Precision → Faithfulness → Answer Relevancy
    - LLM-as-Judge: rubric scoring 1-5, detect bias (positional, verbosity, self-preference)
    - Golden dataset: stratified sampling (5 Easy + 7 Medium + 5 Hard + 3 Adversarial)
    - Failure taxonomy: hallucination, irrelevant, incomplete, off_topic, refusal
    - 5 Whys method for root cause analysis
    - CI/CD integration: eval as quality gate (score < threshold = block deploy)
    - Continuous Improvement Loop: Evaluate → Analyze → Improve → Augment → Repeat

Instructions:
    1. Fill in every required section marked with TODO.
    2. Do NOT change class/function signatures. The optional ``contexts``
       parameter in ``run_full_eval`` is part of the required interface.
    3. Copy this file to solution/solution.py when done.
    4. Run: pytest tests/ -v

The reranking helper is an optional bonus exercise and may remain unimplemented.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Task 1 — Data Models (Golden Dataset + Evaluation Results)
# ---------------------------------------------------------------------------

@dataclass
class QAPair:
    question: str
    expected_answer: str
    context: str = ""
    metadata: dict = field(default_factory=dict)
    retrieved_contexts: list = field(default_factory=list)


@dataclass
class EvalResult:
    qa_pair: QAPair
    actual_answer: str
    faithfulness: float
    relevance: float
    completeness: float
    passed: bool
    failure_type: str | None = None
    context_precision: float | None = None
    context_recall: float | None = None

    def overall_score(self) -> float:
        return (self.faithfulness + self.relevance + self.completeness) / 3.0


# ---------------------------------------------------------------------------
# Task 2 — RAGAS Evaluator
# ---------------------------------------------------------------------------

STOPWORDS: set[str] = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "of", "in", "on", "at", "to", "for", "with", "as", "by", "and", "or",
    "it", "its", "this", "that", "these", "those", "from", "into", "than",
}


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    tokens = re.findall(r"\b\w+\b", text.lower())
    return {t for t in tokens if t not in STOPWORDS}


class RAGASEvaluator:

    def evaluate_faithfulness(self, answer: str, context: str) -> float:
        answer_tokens = _tokenize(answer)
        if not answer_tokens:
            return 1.0
        context_tokens = _tokenize(context)
        score = len(answer_tokens & context_tokens) / len(answer_tokens)
        return max(0.0, min(1.0, score))

    def evaluate_relevance(self, answer: str, question: str) -> float:
        question_tokens = _tokenize(question)
        if not question_tokens:
            return 1.0
        answer_tokens = _tokenize(answer)
        score = len(answer_tokens & question_tokens) / len(question_tokens)
        return max(0.0, min(1.0, score))

    def evaluate_completeness(self, answer: str, expected: str) -> float:
        expected_tokens = _tokenize(expected)
        if not expected_tokens:
            return 1.0
        answer_tokens = _tokenize(answer)
        score = len(answer_tokens & expected_tokens) / len(expected_tokens)
        return max(0.0, min(1.0, score))

    def evaluate_context_recall(self, contexts: list[str], expected: str) -> float:
        expected_tokens = _tokenize(expected)
        if not expected_tokens:
            return 1.0
        union_tokens: set[str] = set()
        for chunk in contexts:
            union_tokens |= _tokenize(chunk)
        score = len(expected_tokens & union_tokens) / len(expected_tokens)
        return max(0.0, min(1.0, score))

    def evaluate_context_precision(
        self,
        contexts: list[str],
        expected: str,
        relevance_threshold: float = 0.1,
    ) -> float:
        expected_tokens = _tokenize(expected)
        if not expected_tokens:
            return 1.0
        if not contexts:
            return 0.0

        relevant_flags: list[bool] = []
        for chunk in contexts:
            chunk_tokens = _tokenize(chunk)
            coverage = len(chunk_tokens & expected_tokens) / len(expected_tokens)
            relevant_flags.append(coverage >= relevance_threshold)

        num_relevant = sum(relevant_flags)
        if num_relevant == 0:
            return 0.0

        hits = 0
        precision_sum = 0.0
        for k, is_rel in enumerate(relevant_flags, start=1):
            if is_rel:
                hits += 1
                precision_sum += hits / k

        return max(0.0, min(1.0, precision_sum / num_relevant))

    def run_full_eval(
        self,
        answer: str,
        question: str,
        context: str,
        expected: str,
        contexts: list[str] | None = None,
    ) -> EvalResult:
        faithfulness = self.evaluate_faithfulness(answer, context)
        relevance = self.evaluate_relevance(answer, question)
        completeness = self.evaluate_completeness(answer, expected)

        passed = faithfulness >= 0.5 and relevance >= 0.5 and completeness >= 0.5

        failure_type: str | None = None
        if not passed:
            if faithfulness < 0.3:
                failure_type = "hallucination"
            elif relevance < 0.3:
                failure_type = "irrelevant"
            elif completeness < 0.3:
                failure_type = "incomplete"
            else:
                failure_type = "off_topic"

        context_recall = None
        context_precision = None
        if contexts is not None:
            context_recall = self.evaluate_context_recall(contexts, expected)
            context_precision = self.evaluate_context_precision(contexts, expected)

        qa_pair = QAPair(
            question=question,
            expected_answer=expected,
            context=context,
            retrieved_contexts=list(contexts) if contexts else [],
        )

        return EvalResult(
            qa_pair=qa_pair,
            actual_answer=answer,
            faithfulness=faithfulness,
            relevance=relevance,
            completeness=completeness,
            passed=passed,
            failure_type=failure_type,
            context_precision=context_precision,
            context_recall=context_recall,
        )


def rerank_by_overlap(contexts: list[str], query: str) -> list[str]:
    query_tokens = _tokenize(query)
    return sorted(
        contexts,
        key=lambda c: len(_tokenize(c) & query_tokens),
        reverse=True,
    )


# ---------------------------------------------------------------------------
# Task 3 — LLM Judge
# ---------------------------------------------------------------------------

class LLMJudge:

    def __init__(self, judge_llm_fn: Callable[[str], str]) -> None:
        self.judge_llm_fn = judge_llm_fn

    def score_response(
        self,
        question: str,
        answer: str,
        rubric: dict[str, Any],
    ) -> dict[str, Any]:
        rubric_lines = "\n".join(
            f"- {name}: {desc}" for name, desc in rubric.items()
        )
        prompt = (
            f"Question: {question}\n"
            f"Answer: {answer}\n"
            f"Rubric:\n{rubric_lines}\n"
            "Return JSON with 'scores' (criterion -> 0-1) and 'reasoning'."
        )
        raw = self.judge_llm_fn(prompt)

        default_scores = {name: 0.5 for name in rubric}
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1:
                raise ValueError("no JSON object found")
            parsed = json.loads(raw[start:end + 1])
            scores = parsed.get("scores", {})
            normalized: dict[str, float] = {}
            for name in rubric:
                val = scores.get(name, 0.5)
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    val = 0.5
                normalized[name] = max(0.0, min(1.0, val))
            reasoning = str(parsed.get("reasoning", raw))
            return {"scores": normalized, "reasoning": reasoning}
        except Exception:
            return {"scores": default_scores, "reasoning": raw}

    def detect_bias(self, scores_batch: list[dict[str, Any]]) -> dict[str, Any]:
        positional_bias = False
        if scores_batch:
            first_higher = 0
            for entry in scores_batch:
                scores = entry.get("scores", {})
                if not scores:
                    continue
                values = list(scores.values())
                if len(values) >= 2 and values[0] > values[-1]:
                    first_higher += 1
            if scores_batch and first_higher / len(scores_batch) > 0.7:
                positional_bias = True

        all_scores: list[float] = []
        for entry in scores_batch:
            all_scores.extend(entry.get("scores", {}).values())

        leniency_bias = False
        severity_bias = False
        if all_scores:
            avg = sum(all_scores) / len(all_scores)
            leniency_bias = avg > 0.8
            severity_bias = avg < 0.3

        return {
            "positional_bias": positional_bias,
            "leniency_bias": leniency_bias,
            "severity_bias": severity_bias,
        }


# ---------------------------------------------------------------------------
# Task 4 — Benchmark Runner
# ---------------------------------------------------------------------------

class BenchmarkRunner:

    def run(
        self,
        qa_pairs: list[QAPair],
        agent_fn: Callable[[str], str],
        evaluator: RAGASEvaluator,
    ) -> list[EvalResult]:
        results: list[EvalResult] = []
        for pair in qa_pairs:
            answer = agent_fn(pair.question)
            contexts = pair.retrieved_contexts or None
            result = evaluator.run_full_eval(
                answer=answer,
                question=pair.question,
                context=pair.context,
                expected=pair.expected_answer,
                contexts=contexts,
            )
            result.qa_pair = pair
            results.append(result)
        return results

    def generate_report(self, results: list[EvalResult]) -> dict[str, Any]:
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        pass_rate = passed / total if total else 0.0

        def avg(values: list[float]) -> float:
            return sum(values) / len(values) if values else 0.0

        avg_faithfulness = avg([r.faithfulness for r in results])
        avg_relevance = avg([r.relevance for r in results])
        avg_completeness = avg([r.completeness for r in results])

        recall_values = [r.context_recall for r in results if r.context_recall is not None]
        precision_values = [r.context_precision for r in results if r.context_precision is not None]

        avg_context_recall = avg(recall_values) if recall_values else None
        avg_context_precision = avg(precision_values) if precision_values else None

        failure_types: dict[str, int] = {}
        for r in results:
            if r.failure_type:
                failure_types[r.failure_type] = failure_types.get(r.failure_type, 0) + 1

        return {
            "total": total,
            "passed": passed,
            "pass_rate": pass_rate,
            "avg_faithfulness": avg_faithfulness,
            "avg_relevance": avg_relevance,
            "avg_completeness": avg_completeness,
            "avg_context_recall": avg_context_recall,
            "avg_context_precision": avg_context_precision,
            "failure_types": failure_types,
        }

    def run_regression(self, new_results: list, baseline_results: list) -> dict:
        def avg_metric(results: list, attr: str) -> float:
            values = [getattr(r, attr) for r in results]
            return sum(values) / len(values) if values else 0.0

        metrics = ["faithfulness", "relevance", "completeness"]
        report: dict[str, Any] = {}
        regressions: list[str] = []

        for m in metrics:
            new_avg = avg_metric(new_results, m)
            base_avg = avg_metric(baseline_results, m)
            report[f"new_avg_{m}"] = new_avg
            report[f"baseline_avg_{m}"] = base_avg
            if base_avg - new_avg > 0.05:
                regressions.append(m)

        report["regressions"] = regressions
        report["passed"] = len(regressions) == 0
        return report

    def identify_failures(
        self,
        results: list[EvalResult],
        threshold: float = 0.5,
    ) -> list[EvalResult]:
        failing: list[EvalResult] = []
        for r in results:
            if (
                r.faithfulness < threshold
                or r.relevance < threshold
                or r.completeness < threshold
            ):
                failing.append(r)
        return failing


# ---------------------------------------------------------------------------
# Task 5 — Failure Analyzer
# ---------------------------------------------------------------------------

class FailureAnalyzer:

    def categorize_failures(self, failures: list[EvalResult]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in failures:
            key = f.failure_type or "unknown"
            counts[key] = counts.get(key, 0) + 1
        return counts

    def find_root_cause(self, failure: EvalResult) -> str:
        f = failure.faithfulness
        r = failure.relevance
        c = failure.completeness

        lowest = min(f, r, c)
        tied = [name for name, val in (("f", f), ("r", r), ("c", c)) if val == lowest]

        if len(tied) > 1:
            return "Multiple issues detected — review full pipeline"
        if tied[0] == "f":
            return "Context is missing or irrelevant — improve retrieval"
        if tied[0] == "r":
            return "Answer does not address the question — improve prompt clarity"
        return "Answer is missing key information — increase context window or improve generation"

    def generate_improvement_log(self, failures: list, suggestions: list[str]) -> str:
        lines = [
            "| Failure ID | Type | Root Cause | Suggested Fix | Status |",
            "|------------|------|------------|---------------|--------|",
        ]
        for i, f in enumerate(failures, start=1):
            fid = f"F{i:03d}"
            ftype = f.failure_type or "unknown"
            cause = self.find_root_cause(f)
            fix = suggestions[i - 1] if i - 1 < len(suggestions) else "Review pipeline"
            lines.append(f"| {fid} | {ftype} | {cause} | {fix} | Open |")
        return "\n".join(lines)

    def generate_improvement_suggestions(
        self, failures: list[EvalResult]
    ) -> list[str]:
        if not failures:
            return []

        categories = self.categorize_failures(failures)
        suggestions: list[str] = []

        if "hallucination" in categories:
            suggestions.append(
                "Implement hallucination checker to filter unsupported claims"
            )
        if "incomplete" in categories:
            suggestions.append(
                "Increase chunk size in RAG pipeline to reduce context fragmentation"
            )
            suggestions.append(
                "Add few-shot examples showing complete answers to improve completeness"
            )
        if "irrelevant" in categories:
            suggestions.append(
                "Improve prompt clarity and intent detection to keep answers on topic"
            )
        if "off_topic" in categories:
            suggestions.append(
                "Add intent classification guardrail to redirect off-topic queries"
            )

        defaults = [
            "Review retrieval pipeline and rerank chunks by relevance",
            "Expand golden dataset with adversarial cases to catch edge failures",
            "Calibrate LLM judge against human labels to reduce scoring drift",
        ]
        for d in defaults:
            if len(suggestions) >= 3:
                break
            if d not in suggestions:
                suggestions.append(d)

        return suggestions


# ---------------------------------------------------------------------------
# Entry point for manual testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    qa_pairs = [
        QAPair(
            question="What is RAG?",
            expected_answer="RAG stands for Retrieval-Augmented Generation, which combines retrieval with text generation.",
            context="RAG is a technique that retrieves relevant documents and uses them to ground LLM generation.",
            metadata={"difficulty": "easy", "category": "definition"},
        ),
        QAPair(
            question="What is the capital of France?",
            expected_answer="Paris is the capital of France.",
            context="France is a country in Western Europe. Its capital city is Paris.",
            metadata={"difficulty": "easy", "category": "factual"},
        ),
        QAPair(
            question="Explain backpropagation and why it matters for training",
            expected_answer="Backpropagation is an algorithm for training neural networks by computing gradients efficiently, enabling deep learning models to learn from errors.",
            context="Neural networks learn through gradient descent. Backpropagation efficiently computes these gradients layer by layer.",
            metadata={"difficulty": "medium", "category": "explanation"},
        ),
        QAPair(
            question="Should I use RAG or fine-tuning for my chatbot?",
            expected_answer="It depends on the use case: RAG is better for frequently updated knowledge, fine-tuning for consistent style/behavior. Consider cost, latency, and data freshness.",
            context="RAG retrieves external documents at inference time. Fine-tuning modifies model weights during training.",
            metadata={"difficulty": "hard", "category": "comparison"},
        ),
        QAPair(
            question="What is the meaning of life?",
            expected_answer="This question is outside the scope of this system. I can help with AI and technology questions.",
            context="This is an AI assistant specialized in technology topics.",
            metadata={"difficulty": "adversarial", "category": "out_of_scope"},
        ),
    ]

    evaluator = RAGASEvaluator()
    runner = BenchmarkRunner()

    def mock_agent(question: str) -> str:
        return f"Based on my knowledge: {question[:30]}... The answer involves key concepts."

    results = runner.run(qa_pairs, mock_agent, evaluator)
    report = runner.generate_report(results)
    print("=== Benchmark Report ===")
    for k, v in report.items():
        print(f"  {k}: {v}")

    failures = runner.identify_failures(results, threshold=0.5)
    print(f"\n=== Failures ({len(failures)}) ===")
    analyzer = FailureAnalyzer()

    categories = analyzer.categorize_failures(failures)
    print("Failure Categories:", categories)

    for f in failures:
        cause = analyzer.find_root_cause(f)
        print(f"  Root cause: {cause}")

    suggestions = analyzer.generate_improvement_suggestions(failures)
    print("\nImprovement Suggestions:")
    for s in suggestions:
        print(f"  - {s}")

    log = analyzer.generate_improvement_log(failures, suggestions)
    print("\n=== Improvement Log ===")
    print(log)