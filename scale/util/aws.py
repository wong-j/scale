"""Utility functions for testing AWS credentials and access to required resources"""
import logging
from collections import namedtuple

from boto3 import Session
from botocore.config import Config
from botocore.exceptions import ClientError
from django.conf import settings

from util.exceptions import InvalidAWSCredentials, FileDoesNotExist

logger = logging.getLogger(__name__)

AWSCredentials = namedtuple('AWSCredentials', ['access_key_id', 'secret_access_key'])


class AWSClient(object):
    """Manages automatically creating and destroying clients to AWS services."""

    def __init__(self, resource, config, credentials=None, region_name=None):
        """Constructor

        :param resource: AWS specific token for resource type. e.g., 's3', 'sqs', etc.
        :type resource: string
        :param config: Resource specific configuration
        :type config: :class:`botocore.client.Config`
        :param credentials: Authentication values needed to access AWS. If no credentials are passed, then IAM
            role-based access is assumed.
        :type credentials: :class:`util.aws.AWSCredentials`
        :param region_name: The AWS region the resource resides in.
        :type region_name: string
        """

        self.credentials = credentials
        self.region_name = region_name
        self._client = None
        self._resource_name = resource
        self._config = config

    def __enter__(self):
        """Callback handles creating a new client for AWS access."""

        logger.debug('Setting up AWS client...')

        session_args = {}
        if self.credentials:
            session_args['aws_access_key_id'] = self.credentials.access_key_id
            session_args['aws_secret_access_key'] = self.credentials.secret_access_key
        if self.region_name:
            session_args['region_name'] = self.region_name
        self._session = Session(**session_args)

        self._client = self._session.client(self._resource_name, config=self._config)
        self._resource = self._session.resource(self._resource_name, config=self._config)
        return self

    def __exit__(self, type, value, traceback):
        """Callback handles destroying an existing client."""
        pass

    @staticmethod
    def instantiate_credentials_from_config(config):
        if 'credentials' in config and config['credentials']:
            credentials_dict = config['credentials']
            if 'access_key_id' not in credentials_dict or not credentials_dict['access_key_id']:
                raise InvalidAWSCredentials('"credentials" requires "access_key_id" to be populated')
            if 'secret_access_key' not in credentials_dict or not credentials_dict['secret_access_key']:
                raise InvalidAWSCredentials('"credentials" requires "secret_access_key" to be populated')
            return AWSCredentials(credentials_dict['access_key_id'], credentials_dict['secret_access_key'])


class SQSClient(AWSClient):
    def __init__(self, credentials=None, region_name=None):
        """Constructor

        :param credentials: Authentication values needed to access AWS. If no credentials are passed, then IAM
            role-based access is assumed.
        :type credentials: :class:`util.aws.AWSCredentials`
        :param region_name: The AWS region the resource resides in.
        :type region_name: string
        """
        AWSClient.__init__(self, 'sqs', None, credentials, region_name)

    def get_queue_by_name(self, queue_name):
        """Gets a SQS queue by the given name

        :param queue_name: The unique name of the SQS queue
        :type queue_name: string
        :return: Queue resource to perform queue operations
        :rtype: :class:`boto3.sqs.Queue`
        """

        return self._resource.get_queue_by_name(QueueName=queue_name)


class S3Client(AWSClient):
    def __init__(self, credentials=None, region_name=None):
        """Constructor

        :param credentials: Authentication values needed to access AWS. If no credentials are passed, then IAM
            role-based access is assumed.
        :type credentials: :class:`util.aws.AWSCredentials`
        :param region_name: The AWS region the resource resides in.
        :type region_name: string
        """
        config = Config(s3={'addressing_style': getattr(settings, 'S3_ADDRESSING_STYLE', 'auto')})
        AWSClient.__init__(self, 's3', config, credentials, region_name)

    def get_bucket(self, bucket_name, validate=True):
        """Gets a reference to an S3 bucket with the given identifier.

        :param bucket_name: The unique name of the bucket to retrieve.
        :type bucket_name: string
        :param validate: Whether to perform a request that verifies the bucket actually exists.
        :type validate: bool
        :returns: The bucket object for the given name.
        :rtype: :class:`boto3.s3.Bucket`

        :raises :class:`botocore.exceptions.ClientError`: If the bucket fails to validate.
        """

        logger.debug('Accessing S3 bucket: %s', bucket_name)
        if validate:
            self._client.head_bucket(Bucket=bucket_name)
        return self._resource.Bucket(bucket_name)

    def get_object(self, bucket_name, key_name, validate=True):
        """Gets a reference to an S3 object with the given identifier.

        :param bucket_name: The unique name of the bucket to retrieve.
        :type bucket_name: string
        :param key_name: The unique name of the object to retrieve that is associated with a file.
        :type key_name: string
        :param validate: Whether to perform a request that verifies the object actually exists.
        :type validate: bool
        :returns: The S3 object for the given name.
        :rtype: :class:`boto3.s3.Object`

        :raises :class:`botocore.exceptions.ClientError`: If the request is invalid.
        :raises :class:`storage.exceptions.FileDoesNotExist`: If the file is not found in the bucket.
        """
        s3_object = self._resource.Object(bucket_name, key_name)

        try:
            if validate:
                s3_object.get()
        except ClientError as err:
            error_code = err.response['ResponseMetadata']['HTTPStatusCode']
            if error_code == 404:
                raise FileDoesNotExist('Unable to access remote file: %s %s' % (bucket_name, key_name))
            raise
        return s3_object





