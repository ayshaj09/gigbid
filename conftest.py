"""Tests always use the hand-made fixtures, even after `datapipe.build` has produced real personas."""
import os

os.environ.setdefault("GIGBID_PERSONA_SOURCE", "fixtures")
