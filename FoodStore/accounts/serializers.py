from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    confirm_password = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'confirm_password', 'role', 'phone']
        extra_kwargs = {
            'username': {'required': True},
            'email': {'required': True},
            'role': {'required': True},
            'phone': {'required': False, 'allow_blank': True},
        }
    
    def validate_username(self, value):
        """Check that username is unique"""
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        if len(value) < 3:
            raise serializers.ValidationError("Username must be at least 3 characters.")
        return value
    
    def validate_email(self, value):
        """Check that email is unique"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value
    
    def validate_phone(self, value):
        """Validate phone number format"""
        if value:
            # Remove any non-digit characters
            cleaned = ''.join(filter(str.isdigit, value))
            if len(cleaned) < 9:
                raise serializers.ValidationError("Phone number must be at least 9 digits.")
        return value
    
    def validate_role(self, value):
        """Validate role is valid"""
        valid_roles = ['customer', 'restaurant', 'driver', 'admin']
        if value not in valid_roles:
            raise serializers.ValidationError(f"Role must be one of: {', '.join(valid_roles)}")
        return value
    
    def validate(self, data):
        """Check that passwords match"""
        password = data.get('password')
        confirm_password = data.get('confirm_password')
        
        if confirm_password and password != confirm_password:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        
        return data
    
    def create(self, validated_data):
        # Remove confirm_password if present
        validated_data.pop('confirm_password', None)
        
        # Create user with proper role
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            role=validated_data['role'],
            phone=validated_data.get('phone', ''),
        )
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role', 'phone', 'is_active', 'date_joined']
        read_only_fields = ['id', 'is_active', 'date_joined']


class UserDetailSerializer(serializers.ModelSerializer):
    """Detailed user serializer with all fields for admin/restaurant views"""
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role', 'phone', 'first_name', 'last_name', 
                  'is_active', 'is_staff', 'date_joined', 'last_login']
        read_only_fields = ['id', 'date_joined', 'last_login']


class PublicUserSerializer(serializers.ModelSerializer):
    """Public user serializer (limited info for public views)"""
    class Meta:
        model = User
        fields = ['id', 'username', 'role']