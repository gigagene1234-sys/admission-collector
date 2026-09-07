package com.admissionhub.collector.canonical

/**
 * Pure policy for v0.10.3 official-table structural binding.
 *
 * Accepted application binding is still conservative:
 * 1) same row contains both department and admission, OR
 * 2) an explicit scope row such as "모집단위 | <전형>" / "해당전형 | <전형>"
 *    starts a block in the SAME official table and the target department appears before
 *    the next explicit scope row.
 *
 * University-wide mentions without an explicit scope row never propagate to departments.
 */
object AdigaOfficialTableBindingPolicy {
    data class SegmentBinding(
        val scopeRowIndex: Int,
        val departmentRowIndex: Int,
        val admissionMatch: String,
        val departmentMatch: String,
        val scopeLabel: String
    )

    fun findExplicitSegmentBindings(
        rows: List<List<String>>,
        department: String?,
        admission: String?,
        admissionCategory: String?
    ): List<SegmentBinding> {
        val out = mutableListOf<SegmentBinding>()
        val declarationIndexes = rows.indices.filter { isExplicitScopeDeclaration(rows[it]) }
        for ((position, scopeIndex) in declarationIndexes.withIndex()) {
            val scopeCells = rows[scopeIndex]
            val admissionQuality = admissionEvidenceQuality(scopeCells, admission, admissionCategory)
            if (admissionQuality != "exact") continue
            val endExclusive = declarationIndexes.getOrNull(position + 1) ?: rows.size
            for (ri in (scopeIndex + 1) until endExclusive) {
                val deptQuality = departmentEvidenceQuality(rows[ri], department)
                if (deptQuality !in setOf("exact", "suffix-equivalent")) continue
                out += SegmentBinding(
                    scopeRowIndex = scopeIndex,
                    departmentRowIndex = ri,
                    admissionMatch = admissionQuality,
                    departmentMatch = deptQuality,
                    scopeLabel = scopeCells.firstOrNull().orEmpty().trim().take(80)
                )
            }
        }
        return out
    }

    fun isExplicitScopeDeclaration(cells: List<String>): Boolean {
        val first = normalize(cells.firstOrNull())
        if (first.isBlank()) return false
        return first == "모집단위" || first.startsWith("모집단위명") ||
            first == "해당전형" || first == "전형명" || first == "모집전형"
    }

    fun admissionEvidenceQuality(cells: List<String>, admission: String?, category: String?): String {
        var best = "none"
        for (cell in cells) {
            when (cellAdmissionQuality(cell, admission, category)) {
                "exact" -> return "exact"
                "related" -> if (best !in setOf("exact")) best = "related"
                "category-only" -> if (best == "none") best = "category-only"
            }
        }
        return best
    }

    fun departmentEvidenceQuality(cells: List<String>, department: String?): String {
        var best = "none"
        for (cell in cells) {
            when (departmentMatchQuality(department, cell)) {
                "exact" -> return "exact"
                "suffix-equivalent" -> best = "suffix-equivalent"
            }
        }
        return best
    }

    fun departmentMatchQuality(left: String?, right: String?): String {
        val l = normalize(left)
        val r = normalize(right)
        if (l.isBlank() || r.isBlank()) return "missing"
        if (l == r) return "exact"
        val suffixes = listOf("학과", "학부", "전공")
        if (suffixes.any { l + it == r || r + it == l }) return "suffix-equivalent"
        return "none"
    }

    private fun cellAdmissionQuality(cellRaw: String, admission: String?, category: String?): String {
        val target = normalizeAdmission(admission)
        val cell = normalizeAdmission(cellRaw)
        val categoryKey = normalizeAdmission(category)
        if (target.isBlank() && categoryKey.isBlank()) return "none"

        val targetVariants = variantSet(admission.orEmpty())
        val cellVariants = variantSet(cellRaw)
        val variantCompatible = when {
            targetVariants.isEmpty() -> true
            cellVariants.isEmpty() -> false
            cellVariants.size > 1 && targetVariants.size == 1 -> false
            else -> targetVariants.all { it in cellVariants }
        }

        if (target.isNotBlank() && variantCompatible) {
            if (cell == target) return "exact"
            if (target.length >= 3 && cell.contains(target)) return "exact"
            if (semanticAdmissionMatch(admission.orEmpty(), cellRaw)) return "exact"
        }
        if (target.isNotBlank() && (cell.contains(target) || target.contains(cell))) return "related"
        if (sameCategory(admission.orEmpty(), cellRaw) && target.isNotBlank()) return "related"
        if (categoryKey.isNotBlank() && normalize(cellRaw).contains(categoryKey)) return "category-only"
        return "none"
    }

    private fun semanticAdmissionMatch(targetRaw: String, cellRaw: String): Boolean {
        val targetCategory = categoryToken(targetRaw) ?: return false
        val cellCategory = categoryToken(cellRaw) ?: return false
        if (targetCategory != cellCategory) return false

        val targetVariants = variantSet(targetRaw)
        val cellVariants = variantSet(cellRaw)
        if (targetVariants.isNotEmpty()) {
            if (cellVariants.isEmpty() || cellVariants.size > 1 || !targetVariants.all { it in cellVariants }) return false
        }

        val targetModifiers = modifierTokens(targetRaw)
        val cellModifiers = modifierTokens(cellRaw)
        if (targetModifiers.isEmpty()) return targetVariants.isNotEmpty() && targetVariants == cellVariants
        return targetModifiers.all { it in cellModifiers }
    }

    private fun sameCategory(a: String, b: String): Boolean {
        val ca = categoryToken(a) ?: return false
        val cb = categoryToken(b) ?: return false
        return ca == cb
    }

    private fun categoryToken(value: String): String? {
        val n = normalize(value)
        return when {
            "종합" in n -> "종합"
            "교과" in n -> "교과"
            else -> null
        }
    }

    private fun modifierTokens(value: String): Set<String> {
        val n = normalize(value)
        val tokens = linkedSetOf<String>()
        val known = listOf(
            "지역인재", "일반", "면접", "자기추천", "학교장추천", "고른기회",
            "농어촌", "기회균형", "사회기여", "배려", "특성화고", "자율전공",
            "중심", "서류형", "서류"
        )
        for (token in known) if (token in n) tokens += token
        return tokens
    }

    private fun variantSet(value: String): Set<Int> {
        val out = linkedSetOf<Int>()
        if ('Ⅰ' in value) out += 1
        if ('Ⅱ' in value) out += 2
        val upper = value.uppercase()
        if (Regex("(^|[^A-Z])I([^A-Z]|$)").containsMatchIn(upper)) out += 1
        if (Regex("(^|[^A-Z])II([^A-Z]|$)").containsMatchIn(upper)) out += 2
        return out
    }

    private fun normalizeAdmission(value: String?): String = normalize(value)
        .replace("학생부", "")
        .replace("전형", "")

    private fun normalize(value: String?): String = value.orEmpty()
        .trim()
        .lowercase()
        .replace("Ⅰ", "1")
        .replace("Ⅱ", "2")
        .replace(Regex("[\\s·・ㆍ_\\-\\/\\[\\]\\(\\)]"), "")
        .replace(Regex("[^0-9a-z가-힣]"), "")
}
