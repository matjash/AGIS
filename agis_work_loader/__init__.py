# -*- coding: utf-8 -*-

# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name

    from .agis_work_loader import ArheoloskiGisWorkLoader
    return ArheoloskiGisWorkLoader(iface)
