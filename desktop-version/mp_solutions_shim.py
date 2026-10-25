"""
Compatibility shim: EyeGestures 3.x was written for the old mediapipe
`mp.solutions.face_mesh` API, which newer mediapipe removed. This recreates
the small part it uses, on top of the new FaceLandmarker task.
Import this BEFORE importing eyeGestures.
"""
import os
import types
import urllib.request

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision
from mediapipe.tasks.python.vision.face_landmarker import FaceLandmarksConnections

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "face_landmarker.task")
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/latest/face_landmarker.task")


def _pairs(connections):
    return frozenset((c.start, c.end) for c in connections)


class _Face:
    def __init__(self, landmarks):
        self.landmark = landmarks


class _Result:
    def __init__(self, faces):
        self.multi_face_landmarks = faces or None


class FaceMesh:
    def __init__(self, **kwargs):
        if not os.path.exists(MODEL_PATH):
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        self._lm = vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=MODEL_PATH),
                num_faces=1))

    def process(self, rgb_image):
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)
        r = self._lm.detect(img)
        return _Result([_Face(f) for f in r.face_landmarks])


if not hasattr(mp, "solutions"):
    face_mesh = types.SimpleNamespace(
        FaceMesh=FaceMesh,
        FACEMESH_LEFT_EYE=_pairs(FaceLandmarksConnections.FACE_LANDMARKS_LEFT_EYE),
        FACEMESH_RIGHT_EYE=_pairs(FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_EYE),
    )
    mp.solutions = types.SimpleNamespace(face_mesh=face_mesh)
