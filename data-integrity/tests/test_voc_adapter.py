"""
Unit tests for PASCAL VOC2012 Dataset Adapter and XML Parser.
"""

import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
import pytest

from src.voc_adapter import VOC2012Adapter, parse_voc_xml, VOC_CLASSES, InvalidAnnotationError


SAMPLE_VALID_XML = """<annotation>
    <folder>VOC2012</folder>
    <filename>2007_000027.jpg</filename>
    <size>
        <width>486</width>
        <height>500</height>
        <depth>3</depth>
    </size>
    <segmented>0</segmented>
    <object>
        <name>person</name>
        <pose>Unspecified</pose>
        <truncated>0</truncated>
        <difficult>0</difficult>
        <bndbox>
            <xmin>174</xmin>
            <ymin>101</ymin>
            <xmax>349</xmax>
            <ymax>351</ymax>
        </bndbox>
    </object>
</annotation>"""

SAMPLE_INVALID_COORDS_XML = """<annotation>
    <filename>bad_coords.jpg</filename>
    <size><width>100</width><height>100</height><depth>3</depth></size>
    <object>
        <name>dog</name>
        <bndbox>
            <xmin>80</xmin><ymin>80</ymin><xmax>20</xmax><ymax>20</ymax>
        </bndbox>
    </object>
</annotation>"""

SAMPLE_OUT_OF_BOUNDS_XML = """<annotation>
    <filename>oob.jpg</filename>
    <size><width>100</width><height>100</height><depth>3</depth></size>
    <object>
        <name>cat</name>
        <bndbox>
            <xmin>10</xmin><ymin>10</ymin><xmax>150</xmax><ymax>80</ymax>
        </bndbox>
    </object>
</annotation>"""

SAMPLE_UNKNOWN_CLASS_XML = """<annotation>
    <filename>unknown.jpg</filename>
    <size><width>100</width><height>100</height><depth>3</depth></size>
    <object>
        <name>alien_spacecraft</name>
        <bndbox>
            <xmin>10</xmin><ymin>10</ymin><xmax>80</xmax><ymax>80</ymax>
        </bndbox>
    </object>
</annotation>"""


def test_parse_valid_xml():
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
        f.write(SAMPLE_VALID_XML)
        tmp_path = Path(f.name)
    try:
        width, height, depth, objects = parse_voc_xml(tmp_path)
        assert len(objects) == 1
        obj = objects[0]
        assert obj.class_name == "person"
        assert obj.xmin == 174
        assert obj.ymin == 101
        assert obj.xmax == 349
        assert obj.ymax == 351
        assert obj.truncated is False
    finally:
        os.remove(tmp_path)


def test_parse_invalid_coordinates_raises_error():
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
        f.write(SAMPLE_INVALID_COORDS_XML)
        tmp_path = Path(f.name)
    try:
        with pytest.raises(InvalidAnnotationError, match="Degenerate bbox"):
            parse_voc_xml(tmp_path)
    finally:
        os.remove(tmp_path)


def test_parse_out_of_bounds_coordinates():
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
        f.write(SAMPLE_OUT_OF_BOUNDS_XML)
        tmp_path = Path(f.name)
    try:
        with pytest.raises(InvalidAnnotationError, match="exceeds image boundaries"):
            parse_voc_xml(tmp_path)
    finally:
        os.remove(tmp_path)


def test_parse_unknown_class():
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
        f.write(SAMPLE_UNKNOWN_CLASS_XML)
        tmp_path = Path(f.name)
    try:
        with pytest.raises(InvalidAnnotationError, match="Unknown class"):
            parse_voc_xml(tmp_path)
    finally:
        os.remove(tmp_path)


def test_deterministic_sample_id():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "JPEGImages"))
        os.makedirs(os.path.join(tmpdir, "Annotations"))
        adapter = VOC2012Adapter(tmpdir)
        id1 = adapter.generate_sample_id("2007_000027")
        id2 = adapter.generate_sample_id("2007_000027")
        assert id1 == "voc2012_2007_000027"
        assert id1 == id2
