from floorplan.source_validation import validate_source_rectangles


def test_source_polygon_must_stay_inside_its_piece_rectangle():
    pieces = [{
        'label': '1',
        'x': 0, 'y': 0, 'wid': 20, 'len': 30,
        'polygon': [(0, 0), (25, 0), (20, 30), (0, 30), (0, 0)],
    }]

    errors = validate_source_rectangles(
        pieces, length=100, width=20, kerf=1,
    )

    assert any('切割轮廓超出所属源片' in error for error in errors)
