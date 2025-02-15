'''for when you don't care about rdf or gatherbaskets, just want metadata about a thing.
'''
import typing

from osf.models.base import coerce_guid
from osf.metadata.osf_gathering import pls_get_magic_metadata_basket
from osf.metadata.serializers import get_metadata_serializer


class SerializedMetadataFile(typing.NamedTuple):
    mediatype: str
    filename: str
    serialized_metadata: str


def pls_gather_metadata_as_primitive(osf_item, format_key, serializer_config=None):
    '''for when you want metadata made of python primitives (e.g. a dictionary)

    @osf_item: the thing (osf model instance or 5-ish character guid string)
    @format_key: str (must be known by osf.metadata.serializers)
    @serializer_config: optional dict (use only when you know the serializer will understand)
    '''
    serializer = get_metadata_serializer(format_key, serializer_config)
    osfguid = coerce_guid(osf_item, create_if_needed=True)
    basket = pls_get_magic_metadata_basket(osfguid.referent)
    return serializer.primitivize(basket)


def pls_gather_metadata_file(osf_item, format_key, serializer_config=None) -> SerializedMetadataFile:
    '''for when you want metadata in a file (for saving or downloading)

    @osf_item: the thing (osf model instance or 5-ish character guid string)
    @format_key: str (must be known by osf.metadata.serializers)
    @serializer_config: optional dict (use only when you know the serializer will understand)
    '''
    serializer = get_metadata_serializer(format_key, serializer_config)
    osfguid = coerce_guid(osf_item, create_if_needed=True)
    basket = pls_get_magic_metadata_basket(osfguid.referent)
    return SerializedMetadataFile(
        serializer.mediatype,
        serializer.filename(osfguid._id),
        serializer.serialize(basket),
    )
