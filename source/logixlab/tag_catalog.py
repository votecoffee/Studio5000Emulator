"""Shared source checks for discovery of tag-backed object catalogs."""

DECLARATIONS = {'tags':'Tags', 'tag':'Tag', 'localtags':'LocalTags',
                'localtag':'LocalTag', 'programs':'Programs', 'program':'Program'}


def complete_tag_source(root, controller):
    """Require complete export context and unambiguous tag declarations.

    Inspect source XML before runtime type filtering. This is a bounded check
    for the catalog readers, not a replacement for native schema validation.
    """
    if (controller is None or root.tag != 'RSLogix5000Content'
            or root.get('TargetType') != 'Controller'
            or root.get('ContainsContext') != 'false'
            or root.findall('Controller') != [controller]
            or controller.get('Use') not in (None, 'Target')
            or len(controller.findall('Tags')) != 1
            or len(controller.findall('Programs')) > 1):
        return False
    for node in controller.iter():
        name = node.tag.rsplit('}', 1)[-1].lower()
        if name in DECLARATIONS:
            if node.tag != DECLARATIONS[name] or node.get('Use') not in (None, 'Target'):
                return False
        if name == 'programs' and any(child.tag != 'Program' for child in node):
            return False
        if name == 'program' and len(node.findall('Tags')) != 1:
            return False
        if name in ('tags', 'localtags'):
            expected = 'Tag' if name == 'tags' else 'LocalTag'
            if any(child.tag != expected or not child.get('DataType') for child in node):
                return False
    return True
