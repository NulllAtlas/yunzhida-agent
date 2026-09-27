from app.schemas import Scene, SceneObject, SceneEvent, TrackPoint


def build_mock_tracking_scene() -> Scene:
    return Scene(
        scene_id="s_mock_rear_end",
        objects=[
            SceneObject(
                id="obj_1",
                kind="vehicle",
                category="car",
                trajectory=[
                    TrackPoint(t=1.0, x=40, y=60, w=8, h=12, speed=0.0, heading=0),
                    TrackPoint(t=2.3, x=34, y=60, w=8, h=12, speed=0.0, heading=0),
                ],
                keyframes=[2.3],
                confidence=0.9,
            ),
            SceneObject(
                id="obj_2",
                kind="vehicle",
                category="car",
                trajectory=[
                    TrackPoint(t=1.0, x=20, y=60, w=8, h=12, speed=6.5, heading=0),
                    TrackPoint(t=2.3, x=24, y=60, w=8, h=12, speed=11.0, heading=0),
                ],
                keyframes=[2.3],
                confidence=0.88,
            ),
        ],
        events=[
            SceneEvent(type="collision", t=2.3, objects=["obj_1", "obj_2"], impact_speed=12.0, confidence=0.82),
        ],
        confidence=0.78,
    )


def build_mock_pedestrian_scene() -> Scene:
    return Scene(
        scene_id="s_mock_pedestrian",
        objects=[
            SceneObject(id="obj_1", kind="vehicle", category="car"),
            SceneObject(id="obj_2", kind="pedestrian", category="person"),
        ],
        events=[SceneEvent(type="collision", t=3.1, objects=["obj_1", "obj_2"], confidence=0.8)],
        confidence=0.72,
    )
