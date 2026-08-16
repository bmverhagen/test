"""Automatische micropatroon-clusters via phrase co-occurrence.

Idee: een micropatroon is geen los ASIN en geen handmatig keyword, maar een
cluster van attributen die op dezelfde long-tail producten samen voorkomen
(bijv. "rice water" + "fermented"). Clusters ontstaan bottom-up uit een
Jaccard-graaf op vooral multi-word phrases — generieke unigrams mogen niet
als brug alles aan elkaar plakken.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from extract import PhraseStats


@dataclass
class MicroPattern:
    cluster_id: str
    label: str
    phrases: list[str]
    asins: set[str] = field(default_factory=set)
    cohesion: float = 0.0  # gemiddelde pairwise Jaccard binnen de cluster

    @property
    def asin_count(self) -> int:
        return len(self.asins)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def _n_words(phrase: str) -> int:
    return len(phrase.split())


def phrase_similarity(
    phrases: dict[str, PhraseStats],
    *,
    min_jaccard: float = 0.28,
) -> dict[str, list[tuple[str, float]]]:
    """Similarity-graaf met strengere regels voor unigrams.

    - Multi-word ↔ multi-word: edge bij jaccard >= min_jaccard
    - Unigram ↔ multi-word: alleen als unigram bijna subset is (jaccard hoog
      én overlap/unigram_df >= 0.7) — unigram hangt aan een specifiek patroon
    - Unigram ↔ unigram: géén edges (voorkomt mega-component via "detox"/"scalp")
    """
    keys = sorted(phrases)
    graph: dict[str, list[tuple[str, float]]] = {k: [] for k in keys}

    def allow_edge(a: str, b: str, j: float) -> bool:
        wa, wb = _n_words(a), _n_words(b)
        if wa >= 2 and wb >= 2:
            return j >= min_jaccard
        if wa >= 2 and wb == 1:
            # unigram b moet grotendeels binnen multi-word a's ASINs vallen
            return j >= min_jaccard and len(phrases[b].asins & phrases[a].asins) / max(
                len(phrases[b].asins), 1
            ) >= 0.7
        if wb >= 2 and wa == 1:
            return j >= min_jaccard and len(phrases[a].asins & phrases[b].asins) / max(
                len(phrases[a].asins), 1
            ) >= 0.7
        return False  # unigram-unigram

    for i, a in enumerate(keys):
        sa = phrases[a].asins
        for b in keys[i + 1 :]:
            j = _jaccard(sa, phrases[b].asins)
            if allow_edge(a, b, j):
                graph[a].append((b, j))
                graph[b].append((a, j))
    return graph


def _connected_components(graph: dict[str, list[tuple[str, float]]]) -> list[list[str]]:
    seen: set[str] = set()
    components: list[list[str]] = []
    for node in graph:
        if node in seen:
            continue
        stack = [node]
        comp: list[str] = []
        seen.add(node)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for nbr, _ in graph[cur]:
                if nbr not in seen:
                    seen.add(nbr)
                    stack.append(nbr)
        components.append(sorted(comp))
    return components


def _mean_cohesion(members: list[str], phrases: dict[str, PhraseStats]) -> float:
    if len(members) < 2:
        return 1.0
    total = 0.0
    pairs = 0
    for i, a in enumerate(members):
        for b in members[i + 1 :]:
            total += _jaccard(phrases[a].asins, phrases[b].asins)
            pairs += 1
    return total / pairs if pairs else 0.0


def _label_cluster(members: list[str], phrases: dict[str, PhraseStats]) -> str:
    """Label = sterkste multi-word phrases (voorkeur bigram/trigram)."""

    def score(p: str) -> tuple[int, int]:
        return (_n_words(p), phrases[p].asin_count)

    ranked = sorted(members, key=score, reverse=True)
    # Skip pure unigrams in label if multi-word beschikbaar
    multi = [p for p in ranked if _n_words(p) >= 2]
    top = (multi or ranked)[:2]
    return " · ".join(top)


def discover_clusters(
    phrases: dict[str, PhraseStats],
    *,
    min_jaccard: float = 0.28,
    min_phrases: int = 1,
    min_asins: int = 3,
    singleton_ok: bool = True,
) -> list[MicroPattern]:
    """Ontdek micropatronen als connected components in de co-occurrence-graaf."""
    graph = phrase_similarity(phrases, min_jaccard=min_jaccard)
    components = _connected_components(graph)

    edged = {n for n, nbrs in graph.items() if nbrs}
    if singleton_ok:
        for phrase, stats in phrases.items():
            if phrase in edged:
                continue
            # Singleton: prefer multi-word; unigrams alleen als DF genoeg
            if _n_words(phrase) == 1 and stats.asin_count < max(min_asins + 1, 4):
                continue
            if stats.asin_count >= min_asins:
                components.append([phrase])

    clusters: list[MicroPattern] = []
    for idx, members in enumerate(components, start=1):
        if len(members) < min_phrases:
            continue
        asins: set[str] = set()
        for p in members:
            asins |= set(phrases[p].asins)
        if len(asins) < min_asins:
            continue
        cohesion = _mean_cohesion(members, phrases)
        # Mega-blob guard: te lage gemiddelde samenhang
        if len(members) > 2 and cohesion < min_jaccard * 0.55:
            continue
        label = _label_cluster(members, phrases)
        members_sorted = sorted(
            members,
            key=lambda p: (_n_words(p), phrases[p].asin_count),
            reverse=True,
        )
        clusters.append(
            MicroPattern(
                cluster_id=f"mp-{idx:03d}",
                label=label,
                phrases=members_sorted,
                asins=asins,
                cohesion=cohesion,
            )
        )

    clusters = _dedup_nested(clusters)
    clusters = _drop_covered_unigrams(clusters)
    clusters.sort(key=lambda c: (-c.asin_count, -len(c.phrases), c.label))
    for i, c in enumerate(clusters, start=1):
        c.cluster_id = f"mp-{i:03d}"
    return clusters


def _drop_covered_unigrams(clusters: list[MicroPattern]) -> list[MicroPattern]:
    """Unigram-only clusters die grotendeels in een multi-word cluster zitten → drop."""
    multi = [c for c in clusters if any(_n_words(p) >= 2 for p in c.phrases)]
    kept: list[MicroPattern] = []
    for c in clusters:
        only_uni = all(_n_words(p) == 1 for p in c.phrases)
        if only_uni and multi:
            covered = max((len(c.asins & m.asins) / max(len(c.asins), 1) for m in multi), default=0.0)
            if covered >= 0.6:
                continue
        kept.append(c)
    return kept


def _dedup_nested(clusters: list[MicroPattern]) -> list[MicroPattern]:
    kept: list[MicroPattern] = []
    for c in sorted(clusters, key=lambda x: (-len(x.phrases), -x.asin_count)):
        dominated = False
        for k in kept:
            if c.asins <= k.asins and set(c.phrases) <= set(k.phrases):
                dominated = True
                break
            inter = len(c.asins & k.asins)
            if inter and inter / max(len(c.asins), 1) > 0.85 and inter / max(len(k.asins), 1) > 0.85:
                if len(c.phrases) <= len(k.phrases):
                    dominated = True
                    break
        if not dominated:
            kept.append(c)
    return kept


def cluster_phrase_owners(clusters: list[MicroPattern]) -> dict[str, str]:
    owners: dict[str, str] = {}
    for c in clusters:
        for p in c.phrases:
            owners.setdefault(p, c.cluster_id)
    return owners
