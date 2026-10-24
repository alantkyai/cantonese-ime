// Project-authored geometry contract checks; no UI, COM or registry operations.
#include "../candidate_layout.h"
#include <cassert>
#include <iostream>
#include <limits>

namespace {
void Bounded(const cime::ui::Layout& layout, int width, int height) {
    assert(layout.width > 0 && layout.width <= width);
    assert(layout.height > 0 && layout.height <= height);
    for (std::size_t i = 0; i < layout.cells.size(); ++i) {
        const auto& cell = layout.cells[i];
        if (cell.Empty()) continue;
        assert(cell.left >= 0 && cell.top >= 0 && cell.right <= layout.width && cell.bottom <= layout.height);
        assert(cime::ui::HitTest(layout, cell.left, cell.top) == static_cast<int>(i));
        assert(cime::ui::HitTest(layout, cell.right - 1, cell.bottom - 1) == static_cast<int>(i));
        for (std::size_t j = 0; j < i; ++j) {
            const auto& other = layout.cells[j];
            if (!other.Empty()) assert(cell.right <= other.left || cell.left >= other.right || cell.bottom <= other.top || cell.top >= other.bottom);
        }
    }
}
} // namespace
int main() {
    using namespace cime::ui;
    assert(MakeLayout({}, 20, 480, 500, 96).cells.empty());
    assert(MakeLayout({34}, 20, 0, 500, 96).cells.empty());
    const auto short_words = MakeLayout(std::vector<int>(9, 34), 20, 480, 500, 96);
    Bounded(short_words, 480, 500);
    assert(short_words.cells.size() == 9 && short_words.width < 480 && short_words.height < 40);
    for (const auto& cell : short_words.cells) assert(cell.top == short_words.cells[0].top);
    assert(HitTest(short_words, 0, 0) == -1);
    assert(HitTest(short_words, short_words.cells[0].right, short_words.cells[0].top) == -1);
    // Representative measured widths include the number, spacing and word as
    // one cell. Labels must trigger wrapping instead of overlapping the next
    // candidate; clicking the leading-label area selects that same candidate.
    const auto numbered_words = MakeLayout(std::vector<int>(9, 51), 20, 480, 500, 96);
    Bounded(numbered_words, 480, 500);
    assert(numbered_words.cells.size() == 9 && numbered_words.height > short_words.height && numbered_words.height < 72);
    for (std::size_t i = 0; i < numbered_words.cells.size(); ++i) {
        const auto& cell = numbered_words.cells[i];
        assert(HitTest(numbered_words, cell.left + numbered_words.text_padding_x + 1, (cell.top + cell.bottom) / 2) == static_cast<int>(i));
    }
    const auto wrapped = MakeLayout({120, 120, 120, 120, 120}, 20, 300, 500, 96);
    Bounded(wrapped, 300, 500);
    assert(wrapped.cells[2].top > wrapped.cells[0].top);
    const auto long_word = MakeLayout({std::numeric_limits<int>::max(), 34}, 20, 480, 500, 96);
    Bounded(long_word, 480, 500);
    assert(long_word.width == 480 && long_word.cells[1].top > long_word.cells[0].top);
    const auto vertical = MakeLayout({34, 120, 51, 34, 90, 34, 80, 51, 34}, 20, 480, 500, 96, 0, CandidateOrientation::Vertical);
    Bounded(vertical, 480, 500);
    assert(vertical.cells.size() == 9 && vertical.width == 138 && vertical.height > short_words.height);
    for (std::size_t i = 0; i < vertical.cells.size(); ++i) {
        assert(vertical.cells[i].left == vertical.cells[0].left && vertical.cells[i].right == vertical.cells[0].right);
        if (i) assert(vertical.cells[i].top > vertical.cells[i - 1].bottom);
    }
    // The default keeps the existing flowing horizontal presentation.
    const auto explicit_horizontal = MakeLayout(std::vector<int>(9, 34), 20, 480, 500, 96, 0, CandidateOrientation::Horizontal);
    assert(explicit_horizontal.width == short_words.width && explicit_horizontal.height == short_words.height);
    for (unsigned dpi : {96u, 120u, 144u, 192u, 240u}) {
        const auto scaled = MakeLayout(std::vector<int>(9, Scale(34, dpi)), Scale(20, dpi), Scale(480, dpi), Scale(500, dpi), dpi);
        Bounded(scaled, Scale(480, dpi), Scale(500, dpi));
        assert(scaled.height <= Scale(40, dpi));
        const auto numbered = MakeLayout(std::vector<int>(9, Scale(51, dpi)), Scale(20, dpi), Scale(480, dpi), Scale(500, dpi), dpi);
        Bounded(numbered, Scale(480, dpi), Scale(500, dpi));
        assert(numbered.height > scaled.height && numbered.height < Scale(72, dpi));
        const auto column = MakeLayout(std::vector<int>(9, Scale(51, dpi)), Scale(20, dpi), Scale(480, dpi), Scale(500, dpi), dpi, 0, CandidateOrientation::Vertical);
        Bounded(column, Scale(480, dpi), Scale(500, dpi));
        assert(column.width < numbered.width && column.height > numbered.height);
        for (const auto& cell : column.cells) assert(!cell.Empty() && cell.left == column.cells[0].left);
    }
    for (int width : {1, 2, 8, 31, 72, 300, 480}) {
        for (int height : {1, 2, 8, 20, 35, 75, 240}) {
            for (const auto orientation : {CandidateOrientation::Horizontal, CandidateOrientation::Vertical}) {
                for (std::size_t selected = 0; selected < 9; ++selected) {
                    const auto small = MakeLayout(std::vector<int>(9, 1000), 20, width, height, 96, selected, orientation);
                    Bounded(small, width, height);
                    assert(!small.cells[selected].Empty());
                    const auto& cell = small.cells[selected];
                    assert(HitTest(small, cell.left, cell.top) == static_cast<int>(selected));
                }
            }
        }
    }
    const Rect work{-1920, -100, 0, 980};
    for (const Rect anchor : {Rect{-10, 970, -1, 980}, Rect{-2500, -500, -2499, -499}, Rect{500, 1500, 501, 1501}}) {
        const auto placed = PlacePopup(short_words, anchor, work, 3);
        assert(placed.left >= work.left && placed.top >= work.top && placed.right <= work.right && placed.bottom <= work.bottom);
    }
    const auto above = PlacePopup(short_words, {-500, 970, -490, 980}, work, 3);
    assert(above.bottom <= 970);
    const auto above_column = PlacePopup(vertical, {-500, 970, -490, 980}, work, 3);
    assert(above_column.bottom <= 970 && above_column.top >= work.top);
    const auto tiny = PlacePopup(long_word, {99, 99, 100, 100}, {0, 0, 10, 10}, 3);
    assert(tiny.left == 0 && tiny.top == 0 && tiny.right == 10 && tiny.bottom == 10);
    std::cout << "Candidate geometry checks passed (horizontal/vertical, equal column widths, wrap, DPI, selected viewport, stable click indices, work-area clamp).\n";
}
