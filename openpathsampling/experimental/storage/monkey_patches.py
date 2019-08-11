import openpathsampling as paths
from .dict_serialization_helpers import (
    tuple_keys_to_dict, tuple_keys_from_dict
)

import importlib
def import_class(full_classname_string):
    splitter = full_classname_string.split('.')
    module_name = ".".join(splitter[:1])
    class_name = splitter[-1]
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    return cls


def callable_cv_from_dict(cls, dct):
    kwargs = dct.pop('kwargs')
    dct.update(kwargs)
    obj = cls(**dct)
    cv_callable= obj.cv_callable
    try:
        cv_callable['_marshal'] = cv_callable['_marshal']['bytes']
    except:
        pass

    cv_callable = paths.netcdfplus.ObjectJSON.callable_from_dict(cv_callable)
    obj.cv_callable = cv_callable
    return obj


def function_pseudo_attribute_to_dict(obj):
    dct = super(paths.netcdfplus.FunctionPseudoAttribute, obj).to_dict()
    cls = dct['key_class']
    dct['key_class'] = cls.__module__ + '.' + cls.__name__
    return dct

def function_pseudo_attribute_from_dict(cls, dct):
    key_class = import_class(dct['key_class'])
    dct['key_clss'] = key_class
    return cls.from_dict(dct)


def monkey_patch_saving(paths):
    paths.netcdfplus.FunctionPseudoAttribute.to_dict = \
            function_pseudo_attribute_to_dict
    paths.TPSNetwork.to_dict = \
            tuple_keys_to_dict(paths.TPSNetwork.to_dict, 'transitions')
    return paths

def monkey_patch_loading(paths):
    paths.CallableCV.from_dict = classmethod(callable_cv_from_dict)
    paths.netcdfplus.FunctionPseudoAttribute.from_dict = \
            classmethod(function_pseudo_attribute_from_dict)
    paths.TPSNetwork.from_dict = \
            classmethod(tuple_keys_from_dict(paths.TPSNetwork.from_dict,
                                             'transitions'))
    return paths

def monkey_patch_all(paths):
    paths = monkey_patch_saving(paths)
    paths = monkey_patch_loading(paths)
    return paths
