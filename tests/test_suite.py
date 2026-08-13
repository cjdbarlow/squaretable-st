import importlib.util


TEST_MODULES = (
    'table_lib_test',
    'table_grid_model_test',
    'table_grid_test',
    'table_list_test',
    'table_package_test',
    'table_plugin_unit_test',
)


def load_tests(loader, unused_tests, unused_pattern):
    package = __package__ or 'tests'
    names = ['{0}.{1}'.format(package, name) for name in TEST_MODULES]
    if importlib.util.find_spec('sublime') is not None:
        names.append('{0}.table_plugin_test'.format(package))
    return loader.loadTestsFromNames(names)
