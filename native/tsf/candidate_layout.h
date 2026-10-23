#pragma once
// Pure geometry for the word-only popup. All inputs/outputs use the host's
// current window-coordinate units; no DPI awareness or Windows state is changed.
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>

namespace cime::ui {
struct Rect {
    int left = 0, top = 0, right = 0, bottom = 0;
    bool Empty() const { return right <= left || bottom <= top; }
    bool Contains(int x, int y) const { return !Empty() && x >= left && x < right && y >= top && y < bottom; }
};
struct Layout {
    int width = 0, height = 0;
    int text_padding_x = 0;
    std::vector<Rect> cells;
};
inline int Scale(int logical, unsigned dpi) {
    return static_cast<int>(std::clamp<std::int64_t>((static_cast<std::int64_t>(logical) * std::max(1u, dpi) + 48) / 96, 1, 16384));
}
inline Layout MakeLayout(const std::vector<int>& text_widths, int text_height,
                         int max_width, int max_height, unsigned dpi,
                         std::size_t selected = 0) {
    Layout result;
    if (text_widths.empty() || max_width <= 0 || max_height <= 0) return result;
    const int outer_x = std::min(Scale(3, dpi), (max_width - 1) / 2);
    const int outer_y = std::min(Scale(3, dpi), (max_height - 1) / 2);
    const int content_width = max_width - 2 * outer_x;
    const int content_height = max_height - 2 * outer_y;
    result.text_padding_x = std::min(Scale(6, dpi), (content_width - 1) / 2);
    const int cell_height = static_cast<int>(std::min<std::int64_t>(content_height,
        std::max(1, text_height) + 2LL * Scale(4, dpi)));
    const int gap = Scale(2, dpi);
    std::int64_t x = outer_x, y = outer_y, used_right = outer_x;
    for (int text_width : text_widths) {
        const int width = static_cast<int>(std::min<std::int64_t>(content_width,
            std::max(1, text_width) + 2LL * result.text_padding_x));
        if (x != outer_x && x + width > max_width - outer_x) { x = outer_x; y += cell_height + gap; }
        // Production pages contain at most nine cells. Fail closed for a geometry
        // input so large that coordinates cannot be represented.
        if (y + cell_height > std::numeric_limits<int>::max() - outer_y) return {};
        result.cells.push_back({static_cast<int>(x), static_cast<int>(y), static_cast<int>(x + width), static_cast<int>(y + cell_height)});
        used_right = std::max(used_right, x + width); x += width + gap;
    }
    result.width = static_cast<int>(used_right + outer_x);
    result.height = static_cast<int>(std::min<std::int64_t>(max_height, y + cell_height + outer_y));
    selected = std::min(selected, result.cells.size() - 1);
    const int scroll = std::max(0, result.cells[selected].bottom - (result.height - outer_y));
    for (auto& cell : result.cells) {
        cell.top -= scroll; cell.bottom -= scroll;
        // A short monitor gets a selected-row viewport, never half-painted words.
        // Off-viewport cells remain available to the TSF/keyboard candidate list.
        if (cell.top < outer_y || cell.bottom > result.height - outer_y) cell = {};
    }
    return result;
}
inline int HitTest(const Layout& layout, int x, int y) {
    for (std::size_t i = 0; i < layout.cells.size(); ++i)
        if (layout.cells[i].Contains(x, y)) return static_cast<int>(i);
    return -1;
}
inline Rect PlacePopup(const Layout& layout, const Rect& anchor, const Rect& work, int gap) {
    if (layout.width <= 0 || layout.height <= 0 || work.Empty()) return {};
    const auto width = std::min<std::int64_t>(layout.width, static_cast<std::int64_t>(work.right) - work.left);
    const auto height = std::min<std::int64_t>(layout.height, static_cast<std::int64_t>(work.bottom) - work.top);
    const auto x = std::clamp<std::int64_t>(anchor.left, work.left, static_cast<std::int64_t>(work.right) - width);
    const auto below = static_cast<std::int64_t>(anchor.bottom) + std::max(0, gap);
    const auto above = static_cast<std::int64_t>(anchor.top) - std::max(0, gap) - height;
    auto y = below;
    if (below + height > work.bottom && above >= work.top) y = above;
    y = std::clamp<std::int64_t>(y, work.top, static_cast<std::int64_t>(work.bottom) - height);
    return {static_cast<int>(x), static_cast<int>(y), static_cast<int>(x + width), static_cast<int>(y + height)};
}
} // namespace cime::ui
