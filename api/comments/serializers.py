from rest_framework import serializers as ser
from framework.guid.model import Guid
from framework.auth.core import Auth
from website.project.model import Node, Comment
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound
from api.base.exceptions import InvalidModelValueError
from api.base.utils import absolute_reverse
from api.base.serializers import (JSONAPISerializer,
                                  JSONAPIHyperlinkedRelatedField,
                                  JSONAPIHyperlinkedGuidRelatedField,
                                  JSONAPIHyperlinkedIdentityField,
                                  IDField, TypeField, LinksField,
                                  AuthorizedCharField)


class CommentReport(object):
    def __init__(self, user_id, category, text):
        self._id = user_id
        self.category = category
        self.text = text


class CommentSerializer(JSONAPISerializer):

    filterable_fields = frozenset([
        'deleted'
    ])

    id = IDField(source='_id', read_only=True)
    type = TypeField()
    content = AuthorizedCharField(source='return_content')

    user = JSONAPIHyperlinkedRelatedField(view_name='users:user-detail', lookup_field='pk', lookup_url_kwarg='user_id', link_type='related', read_only=True)
    node = JSONAPIHyperlinkedRelatedField(view_name='nodes:node-detail', lookup_field='pk', lookup_url_kwarg='node_id', link_type='related', read_only=True)
    target = JSONAPIHyperlinkedGuidRelatedField(link_type='related', meta={'type': 'get_target_type'})
    replies = JSONAPIHyperlinkedIdentityField(view_name='comments:comment-replies', lookup_field='pk', link_type='self', lookup_url_kwarg='comment_id')
    reports = JSONAPIHyperlinkedIdentityField(view_name='comments:comment-reports', lookup_field='pk', lookup_url_kwarg='comment_id', link_type='related', read_only=True)

    date_created = ser.DateTimeField(read_only=True)
    date_modified = ser.DateTimeField(read_only=True)
    modified = ser.BooleanField(read_only=True, default=False)
    deleted = ser.BooleanField(read_only=True, source='is_deleted', default=False)

    # LinksField.to_representation adds link to "self"
    links = LinksField({})

    class Meta:
        type_ = 'comments'

    def create(self, validated_data):
        user = validated_data['user']
        node = validated_data['node']

        validated_data['content'] = validated_data.pop('return_content')
        if node and node.can_comment(Auth(user)):
            comment = Comment.create(auth=Auth(user), **validated_data)
        else:
            raise PermissionDenied("Not authorized to comment on this project.")
        return comment

    def update(self, comment, validated_data):
        assert isinstance(comment, Comment), 'comment must be a Comment'
        auth = Auth(self.context['request'].user)
        if validated_data:
            if 'return_content' in validated_data:
                comment.edit(validated_data['return_content'], auth=auth, save=True)
            is_deleted = validated_data.get('is_deleted', None)
            if is_deleted:
                comment.delete(auth, save=True)
            elif comment.is_deleted:
                comment.undelete(auth, save=True)
        return comment

    def get_target_type(self, obj):
        target_id = obj._id
        guid_object = Guid.load(target_id)
        if not guid_object:
            raise NotFound('Comment target not found.')
        target = guid_object.referent

        if isinstance(target, Node):
            return 'node'
        elif isinstance(target, Comment):
            return 'comment'
        else:
            raise InvalidModelValueError('Invalid comment target.')


class CommentDetailSerializer(CommentSerializer):
    """
    Overrides CommentSerializer to make id required.
    """
    id = IDField(source='_id', required=True)
    deleted = ser.BooleanField(source='is_deleted', required=True)


class CommentReportsSerializer(JSONAPISerializer):
    id = IDField(source='_id', read_only=True)
    type = TypeField()
    category = ser.ChoiceField(choices=[('spam', 'Spam or advertising'),
                                        ('hate', 'Hate speech'),
                                        ('violence', 'Violence or harmful behavior')], required=True)
    message = ser.CharField(source='text', required=False, allow_blank=True)
    links = LinksField({'self': 'get_absolute_url'})

    class Meta:
        type_ = 'comment_reports'

    def get_absolute_url(self, obj):
        comment_id = self.context['request'].parser_context['kwargs']['comment_id']
        return absolute_reverse(
            'comments:report-detail',
            kwargs={
                'comment_id': comment_id,
                'user_id': obj._id
            }
        )

    def create(self, validated_data):
        user = self.context['request'].user
        comment = self.context['view'].get_comment()
        if user._id in comment.reports:
            raise ValidationError('Comment already reported.')
        try:
            comment.report_abuse(user, save=True, **validated_data)
        except ValueError:
            raise ValidationError('You cannot report your own comment.')
        return CommentReport(user._id, **validated_data)

    def update(self, comment_report, validated_data):
        user = self.context['request'].user
        comment = self.context['view'].get_comment()
        if user._id != comment_report._id:
            raise ValidationError('You cannot report a comment on behalf of another user.')
        try:
            comment.report_abuse(user, save=True, **validated_data)
        except ValueError:
            raise ValidationError('You cannot report your own comment.')
        return CommentReport(user._id, **validated_data)


class CommentReportDetailSerializer(CommentReportsSerializer):
    """
    Overrides CommentReportSerializer to make id required.
    """
    id = IDField(source='_id', required=True)
