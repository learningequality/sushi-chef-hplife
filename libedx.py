import json
import os

from bs4 import BeautifulSoup
from bs4.element import NavigableString


def parse_xml_file(coursedir, kind, name, ext='xml'):
    """
    Parse the XML file at {coursedir}/{kind}/{name}.{ext}
    and return the json tree representation.
    References are not resolved --- see `parse_xml_file_refusive` for that.
    """

    # Build path to XML file
    path = coursedir
    if kind:
        path = os.path.join(path, kind)
    path = os.path.join(path, name + '.' + ext)
    if not os.path.exists(path):
        raise ValueError('XML file not found: ' + path)
    
    # Load XML
    xml = open(path, 'r')
    doc = BeautifulSoup(xml, "xml")
    doc_children = list(doc.children)
    assert len(doc_children) == 1, 'Found more than one root element!'
    doc_root = doc_children[0]
    # print(doc)
    
    # JSON data object
    data = {
        'kind': doc_root.name,
        'children': [],
    }
    data.update(doc_root.attrs)
    
    # Add children as unresoled references
    for child in doc_root.children:
        if type(child) == NavigableString:
            continue
        assert len(child.attrs) == 1, 'Assumption failed: encountered more than one attr'
        kind = child.name
        child_ref = {
            'kind': kind,
        }
        if kind == 'wiki':
            child_ref['slug'] = child.attrs['slug']
        elif kind == 'html':
            child_ref['url_name'] = child.attrs['url_name']
            child_ref['ext'] = 'html'
        else:
            child_ref['url_name'] = child.attrs['url_name']
        data['children'].append(child_ref)

    return data



def parse_xml_file_refusive(coursedir, kind, name, ext='xml'):
    """
    Parse the XML file at {coursedir}/{kind}/{name}.{ext} recusively
    using the base XML-to-JSON basic parsing function `parse_xml_file`.
    Recusrively resolves all references of the form {kind: AAA, url_name: BBB}
    bu loading the XML data from the file at {coursedir}/AAA/BBB.xml
    Returns a json tree representation.
    """
    root = parse_xml_file(coursedir, kind, name, ext=ext)
    new_children = []
    for child in root['children']:
        child_kind = child['kind']
        if child_kind in ['wiki', 'html']:
            new_children.append(child)
        elif child_kind in ['problem']:
            new_children.append(child)
        else:
            child_name = child['url_name']
            resolved_child = parse_xml_file_refusive(coursedir, child_kind, child_name, ext='xml')
            new_children.append(resolved_child)
    root['children'] = new_children
    return root




def print_course(course):
    """
    Display course hierarchy
    """
    def print_subtree(subtree, indent=0):
        extra = ''
        if 'url_name' in subtree:
            extra += ' url_name=' + subtree['url_name']
        if 'slug' in subtree:
            extra += ' slug=' + subtree['slug']
        if 'display_name' in subtree:
            title = subtree['display_name']
        else:
            title = ''
        print('   '*indent, '-', title,  'kind='+subtree['kind'], '\t', extra)
        if 'children' in subtree:
            for child in subtree['children']:
                print_subtree(child, indent=indent+1)
    print_subtree(course)

