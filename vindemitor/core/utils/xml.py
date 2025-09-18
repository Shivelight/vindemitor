from typing import Union

from lxml import etree
from lxml.etree import ElementTree


def load_xml(xml: Union[str, bytes]) -> ElementTree:
    """Safely parse XML data to an ElementTree, without namespaces in tags."""
    if not isinstance(xml, bytes):
        xml = xml.encode("utf8")
    root = etree.fromstring(xml)
    for elem in root.getiterator():
        if not hasattr(elem.tag, "find"):
            # e.g. comment elements
            continue
        elem.tag = etree.QName(elem).localname
        for name, value in elem.attrib.items():
            local_name = etree.QName(name).localname
            if local_name == name:
                continue
            del elem.attrib[name]
            elem.attrib[local_name] = value
    etree.cleanup_namespaces(root)
    return root


def matroska_tags_xml(data: dict[str, str | dict]) -> bytes:
    # https://www.matroska.org/technical/tagging.html
    # https://codeberg.org/mbunkus/mkvtoolnix/src/branch/main/examples/example-tags-2.xml
    root = etree.Element("Tags")
    tag = etree.SubElement(root, "Tag")
    etree.SubElement(tag, "Targets")

    def create_simple_element(parent, name, data):
        simple = etree.SubElement(parent, "Simple")
        name_elem = etree.SubElement(simple, "Name")
        name_elem.text = name
        if isinstance(data, dict):
            string = etree.SubElement(simple, "String")
            string.text = data.get("value", "")
            if "nested" in data:
                for nested_name, nested_data in data["nested"].items():
                    create_simple_element(simple, nested_name, nested_data)
        else:
            string = etree.SubElement(simple, "String")
            string.text = str(data)

    for name, value in data.items():
        create_simple_element(tag, name, value)

    xml_string = etree.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)

    return xml_string
