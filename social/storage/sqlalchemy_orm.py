"""Flask SQLAlchemy models for Social Auth"""
import base64

from sqlalchemy.exc import IntegrityError

from social.exceptions import NotAllowedToDisconnect
from social.storage.base import UserMixin, AssociationMixin, NonceMixin, \
                                BaseStorage


class SQLAlchemyMixin(object):
    @classmethod
    def new_instance(cls, model, *args, **kwargs):
        return cls.save_instance(model(*args, **kwargs))

    @classmethod
    def save_instance(cls, instance):
        session = cls.query.session
        session.add(instance)
        session.commit()
        return instance


class SQLAlchemyUserMixin(SQLAlchemyMixin, UserMixin):
    """Social Auth association model"""
    @classmethod
    def changed(cls, user):
        cls.save_instance(user)

    def set_extra_data(self, extra_data=None):
        if super(SQLAlchemyUserMixin, self).set_extra_data(extra_data):
            self.save_instance(self)

    @classmethod
    def allowed_to_disconnect(cls, user, backend_name, association_id=None):
        if association_id is not None:
            qs = cls.query.filter(cls.id != association_id)
        else:
            qs = cls.query.filter(cls.provider != backend_name)
        qs = qs.filter(cls.user == user)

        if hasattr(user, 'has_usable_password'):
            # TODO
            valid_password = user.has_usable_password()
        else:
            valid_password = True
        return valid_password or qs.count() > 0

    @classmethod
    def disconnect(cls, name, user, association_id=None):
        if cls.allowed_to_disconnect(user, name, association_id):
            qs = cls.get_social_auth_for_user(user)
            if association_id:
                qs = qs.filter(cls.id == association_id)
            else:
                qs = qs.filter(cls.provider == name)
            qs.delete()
        else:
            raise NotAllowedToDisconnect()

    @classmethod
    def simple_user_exists(cls, username):
        """
        Return True/False if a User instance exists with the given arguments.
        Arguments are directly passed to filter() manager method.
        """
        User = cls.user_model()
        return User.query.filter(User.username == username).count() > 0

    @classmethod
    def get_username(cls, user):
        return getattr(user, 'username', None)

    @classmethod
    def create_user(cls, username, email=None):
        return cls.new_instance(cls.user_model(), username=username,
                                email=email)

    @classmethod
    def get_user(cls, pk):
        return cls.user_model().query.get(pk)

    @classmethod
    def get_social_auth(cls, provider, uid):
        if not isinstance(uid, basestring):
            uid = str(uid)
        try:
            return cls.query.filter(cls.provider == provider,
                                    cls.uid == uid)[0]
        except IndexError:
            return None

    @classmethod
    def get_social_auth_for_user(cls, user):
        return user.social_auth.query.all()

    @classmethod
    def create_social_auth(cls, user, uid, provider):
        if not isinstance(uid, basestring):
            uid = str(uid)
        return cls.new_instance(cls, user=user, uid=uid, provider=provider)


class SQLAlchemyNonceMixin(SQLAlchemyMixin, NonceMixin):
    @classmethod
    def use(cls, server_url, timestamp, salt):
        kwargs = {'server_url': server_url, 'timestamp': timestamp,
                  'salt': salt}
        try:
            return cls.query.filter_by(**kwargs)[0]
        except IndexError:
            return cls.new_instance(cls, **kwargs)


class SQLAlchemyAssociationMixin(SQLAlchemyMixin, AssociationMixin):
    @classmethod
    def store(cls, server_url, association):
        # Don't use get_or_create because issued cannot be null
        try:
            assoc = cls.query.filter_by(server_url=server_url,
                                        handle=association.handle)[0]
        except IndexError:
            assoc = cls(server_url=server_url,
                        handle=association.handle)
        assoc.secret = base64.encodestring(association.secret)
        assoc.issued = association.issued
        assoc.lifetime = association.lifetime
        assoc.assoc_type = association.assoc_type
        cls.save_instance(assoc)

    @classmethod
    def get(cls, *args, **kwargs):
        return cls.query.filter_by(*args, **kwargs)

    @classmethod
    def remove(cls, ids_to_delete):
        cls.query.filter(cls.id.in_(ids_to_delete)).delete()


class BaseSQLAlchemyStorage(BaseStorage):
    user = SQLAlchemyUserMixin
    nonce = SQLAlchemyNonceMixin
    association = SQLAlchemyAssociationMixin

    def is_integrity_error(self, exception):
        return exception.__class__ is IntegrityError