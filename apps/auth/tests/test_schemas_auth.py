# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.schemas.auth — Authentication schemas."""

import pytest
from auth.api.schemas.auth import (
    ProfileFields,
    RegisterRequest,
    RegisterResponse,
    RegistrationSource,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_PROFILE = {"nickname": "jdoe", "firstname": "John", "lastname": "Doe"}
VALID_PASSWORD = "P@ssw0rd!"


# ---------------------------------------------------------------------------
# ProfileFields — required field validators
# ---------------------------------------------------------------------------


class TestProfileFieldsRequired:
    def test_valid_minimal(self):
        p = ProfileFields(**VALID_PROFILE)
        assert p.nickname == "jdoe"
        assert p.firstname == "John"
        assert p.lastname == "Doe"

    def test_strips_whitespace(self):
        p = ProfileFields(nickname="  jdoe  ", firstname="  John  ", lastname="  Doe  ")
        assert p.nickname == "jdoe"
        assert p.firstname == "John"
        assert p.lastname == "Doe"

    def test_empty_nickname_raises(self):
        with pytest.raises(ValidationError, match="[Nn]ickname"):
            ProfileFields(nickname="", firstname="John", lastname="Doe")

    def test_whitespace_only_nickname_raises(self):
        with pytest.raises(ValidationError):
            ProfileFields(nickname="   ", firstname="John", lastname="Doe")

    def test_empty_firstname_raises(self):
        with pytest.raises(ValidationError, match="[Ff]irstname"):
            ProfileFields(nickname="jdoe", firstname="", lastname="Doe")

    def test_empty_lastname_raises(self):
        with pytest.raises(ValidationError, match="[Ll]astname"):
            ProfileFields(nickname="jdoe", firstname="John", lastname="")

    def test_nickname_too_long_raises(self):
        with pytest.raises(ValidationError, match="255"):
            ProfileFields(nickname="x" * 256, firstname="John", lastname="Doe")

    def test_firstname_too_long_raises(self):
        with pytest.raises(ValidationError, match="255"):
            ProfileFields(nickname="jdoe", firstname="x" * 256, lastname="Doe")

    def test_lastname_too_long_raises(self):
        with pytest.raises(ValidationError, match="255"):
            ProfileFields(nickname="jdoe", firstname="John", lastname="x" * 256)

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            ProfileFields(nickname="jdoe", firstname="John")


# ---------------------------------------------------------------------------
# ProfileFields — optional string validators
# ---------------------------------------------------------------------------


class TestProfileFieldsOptionalStrings:
    def test_middle_name_none(self):
        p = ProfileFields(**VALID_PROFILE, middle_name=None)
        assert p.middle_name is None

    def test_middle_name_stripped(self):
        p = ProfileFields(**VALID_PROFILE, middle_name="  Bob  ")
        assert p.middle_name == "Bob"

    def test_middle_name_empty_becomes_none(self):
        p = ProfileFields(**VALID_PROFILE, middle_name="   ")
        assert p.middle_name is None

    def test_middle_name_too_long_raises(self):
        with pytest.raises(ValidationError, match="255"):
            ProfileFields(**VALID_PROFILE, middle_name="x" * 256)

    def test_preferred_username_valid(self):
        p = ProfileFields(**VALID_PROFILE, preferred_username="johnny")
        assert p.preferred_username == "johnny"

    def test_preferred_username_empty_becomes_none(self):
        p = ProfileFields(**VALID_PROFILE, preferred_username="")
        assert p.preferred_username is None

    def test_preferred_username_too_long_raises(self):
        with pytest.raises(ValidationError, match="255"):
            ProfileFields(**VALID_PROFILE, preferred_username="x" * 256)


# ---------------------------------------------------------------------------
# ProfileFields — URL validators
# ---------------------------------------------------------------------------


class TestProfileFieldsUrls:
    def test_valid_https_url(self):
        p = ProfileFields(**VALID_PROFILE, profile_url="https://example.com/me")
        assert p.profile_url == "https://example.com/me"

    def test_valid_http_url(self):
        p = ProfileFields(**VALID_PROFILE, website="http://example.com")
        assert p.website == "http://example.com"

    def test_url_none(self):
        p = ProfileFields(**VALID_PROFILE, picture_url=None)
        assert p.picture_url is None

    def test_url_empty_becomes_none(self):
        p = ProfileFields(**VALID_PROFILE, profile_url="  ")
        assert p.profile_url is None

    def test_url_too_long_raises(self):
        with pytest.raises(ValidationError, match="2048"):
            ProfileFields(**VALID_PROFILE, profile_url="https://x.com/" + "a" * 2048)

    def test_url_invalid_scheme_raises(self):
        with pytest.raises(ValidationError, match="http"):
            ProfileFields(**VALID_PROFILE, website="ftp://example.com")

    def test_picture_url_valid(self):
        p = ProfileFields(**VALID_PROFILE, picture_url="https://cdn.example.com/avatar.jpg")
        assert p.picture_url == "https://cdn.example.com/avatar.jpg"


# ---------------------------------------------------------------------------
# ProfileFields — birthdate
# ---------------------------------------------------------------------------


class TestProfileFieldsBirthdate:
    def test_valid_birthdate(self):
        p = ProfileFields(**VALID_PROFILE, birthdate="1990-01-15")
        assert p.birthdate == "1990-01-15"

    def test_birthdate_none(self):
        p = ProfileFields(**VALID_PROFILE, birthdate=None)
        assert p.birthdate is None

    def test_birthdate_empty_becomes_none(self):
        p = ProfileFields(**VALID_PROFILE, birthdate="  ")
        assert p.birthdate is None

    def test_birthdate_invalid_format_raises(self):
        with pytest.raises(ValidationError, match="YYYY-MM-DD"):
            ProfileFields(**VALID_PROFILE, birthdate="15/01/1990")

    def test_birthdate_partial_raises(self):
        with pytest.raises(ValidationError, match="YYYY-MM-DD"):
            ProfileFields(**VALID_PROFILE, birthdate="1990-01")


# ---------------------------------------------------------------------------
# ProfileFields — locale / zoneinfo / phone / gender
# ---------------------------------------------------------------------------


class TestProfileFieldsMisc:
    def test_locale_valid(self):
        p = ProfileFields(**VALID_PROFILE, locale="fr-FR")
        assert p.locale == "fr-FR"

    def test_locale_none(self):
        p = ProfileFields(**VALID_PROFILE, locale=None)
        assert p.locale is None

    def test_locale_empty_becomes_none(self):
        p = ProfileFields(**VALID_PROFILE, locale="")
        assert p.locale is None

    def test_locale_too_long_raises(self):
        with pytest.raises(ValidationError, match="10"):
            ProfileFields(**VALID_PROFILE, locale="x" * 11)

    def test_zoneinfo_valid(self):
        p = ProfileFields(**VALID_PROFILE, zoneinfo="Europe/Paris")
        assert p.zoneinfo == "Europe/Paris"

    def test_zoneinfo_none(self):
        p = ProfileFields(**VALID_PROFILE, zoneinfo=None)
        assert p.zoneinfo is None

    def test_zoneinfo_empty_becomes_none(self):
        p = ProfileFields(**VALID_PROFILE, zoneinfo="  ")
        assert p.zoneinfo is None

    def test_zoneinfo_too_long_raises(self):
        with pytest.raises(ValidationError, match="50"):
            ProfileFields(**VALID_PROFILE, zoneinfo="x" * 51)

    def test_phone_valid(self):
        p = ProfileFields(**VALID_PROFILE, phone_number="+33612345678")
        assert p.phone_number == "+33612345678"

    def test_phone_none(self):
        p = ProfileFields(**VALID_PROFILE, phone_number=None)
        assert p.phone_number is None

    def test_phone_empty_becomes_none(self):
        p = ProfileFields(**VALID_PROFILE, phone_number="  ")
        assert p.phone_number is None

    def test_phone_too_long_raises(self):
        with pytest.raises(ValidationError, match="50"):
            ProfileFields(**VALID_PROFILE, phone_number="1" * 51)

    def test_gender_lowered(self):
        p = ProfileFields(**VALID_PROFILE, gender="Male")
        assert p.gender == "male"

    def test_gender_none(self):
        p = ProfileFields(**VALID_PROFILE, gender=None)
        assert p.gender is None

    def test_gender_empty_becomes_none(self):
        p = ProfileFields(**VALID_PROFILE, gender="  ")
        assert p.gender is None

    def test_gender_too_long_raises(self):
        with pytest.raises(ValidationError, match="50"):
            ProfileFields(**VALID_PROFILE, gender="x" * 51)


# ---------------------------------------------------------------------------
# ProfileFields — address fields
# ---------------------------------------------------------------------------


class TestProfileFieldsAddress:
    def test_address_street_valid(self):
        p = ProfileFields(**VALID_PROFILE, address_street="123 Main St")
        assert p.address_street == "123 Main St"

    def test_address_street_none(self):
        p = ProfileFields(**VALID_PROFILE, address_street=None)
        assert p.address_street is None

    def test_address_street_empty_becomes_none(self):
        p = ProfileFields(**VALID_PROFILE, address_street="")
        assert p.address_street is None

    def test_address_street_too_long_raises(self):
        with pytest.raises(ValidationError, match="500"):
            ProfileFields(**VALID_PROFILE, address_street="x" * 501)

    def test_address_locality_valid(self):
        p = ProfileFields(**VALID_PROFILE, address_locality="Paris")
        assert p.address_locality == "Paris"

    def test_address_locality_empty_becomes_none(self):
        p = ProfileFields(**VALID_PROFILE, address_locality="")
        assert p.address_locality is None

    def test_address_locality_too_long_raises(self):
        with pytest.raises(ValidationError, match="255"):
            ProfileFields(**VALID_PROFILE, address_locality="x" * 256)

    def test_address_region_valid(self):
        p = ProfileFields(**VALID_PROFILE, address_region="Ile-de-France")
        assert p.address_region == "Ile-de-France"

    def test_address_region_empty_becomes_none(self):
        p = ProfileFields(**VALID_PROFILE, address_region="  ")
        assert p.address_region is None

    def test_address_region_too_long_raises(self):
        with pytest.raises(ValidationError, match="255"):
            ProfileFields(**VALID_PROFILE, address_region="x" * 256)

    def test_postal_code_valid(self):
        p = ProfileFields(**VALID_PROFILE, address_postal_code="75001")
        assert p.address_postal_code == "75001"

    def test_postal_code_empty_becomes_none(self):
        p = ProfileFields(**VALID_PROFILE, address_postal_code="")
        assert p.address_postal_code is None

    def test_postal_code_too_long_raises(self):
        with pytest.raises(ValidationError, match="50"):
            ProfileFields(**VALID_PROFILE, address_postal_code="x" * 51)

    def test_country_valid(self):
        p = ProfileFields(**VALID_PROFILE, address_country="France")
        assert p.address_country == "France"

    def test_country_empty_becomes_none(self):
        p = ProfileFields(**VALID_PROFILE, address_country="  ")
        assert p.address_country is None

    def test_country_too_long_raises(self):
        with pytest.raises(ValidationError, match="100"):
            ProfileFields(**VALID_PROFILE, address_country="x" * 101)


# ---------------------------------------------------------------------------
# ProfileFields — to_profile_dict
# ---------------------------------------------------------------------------


class TestProfileFieldsToDict:
    def test_minimal(self):
        p = ProfileFields(**VALID_PROFILE)
        d = p.to_profile_dict()
        assert d["nickname"] == "jdoe"
        assert d["given_name"] == "John"
        assert d["family_name"] == "Doe"
        assert d["middle_name"] is None
        assert d["phone_number"] is None

    def test_full(self):
        p = ProfileFields(
            **VALID_PROFILE,
            middle_name="M",
            preferred_username="johnny",
            profile_url="https://example.com",
            picture_url="https://cdn.example.com/pic.jpg",
            website="https://blog.example.com",
            gender="male",
            birthdate="1990-01-15",
            zoneinfo="Europe/Paris",
            locale="fr-FR",
            address_street="123 Main",
            address_locality="Paris",
            address_region="IDF",
            address_postal_code="75001",
            address_country="France",
            phone_number="+33600000000",
        )
        d = p.to_profile_dict()
        assert d["given_name"] == "John"
        assert d["family_name"] == "Doe"
        assert d["middle_name"] == "M"
        assert d["preferred_username"] == "johnny"
        assert d["profile_url"] == "https://example.com"
        assert d["picture_url"] == "https://cdn.example.com/pic.jpg"
        assert d["website"] == "https://blog.example.com"
        assert d["gender"] == "male"
        assert d["birthdate"] == "1990-01-15"
        assert d["zoneinfo"] == "Europe/Paris"
        assert d["locale"] == "fr-FR"
        assert d["address_street"] == "123 Main"
        assert d["address_locality"] == "Paris"
        assert d["address_region"] == "IDF"
        assert d["address_postal_code"] == "75001"
        assert d["address_country"] == "France"
        assert d["phone_number"] == "+33600000000"


# ---------------------------------------------------------------------------
# RegistrationSource
# ---------------------------------------------------------------------------


class TestRegistrationSource:
    def test_defaults(self):
        rs = RegistrationSource()
        assert rs.source == "api"
        assert rs.client_id is None
        assert rs.client_name is None

    def test_direct_source(self):
        rs = RegistrationSource(source="direct")
        assert rs.source == "direct"

    def test_oauth_source(self):
        rs = RegistrationSource(source="oauth", client_id="c1", client_name="My App")
        assert rs.source == "oauth"
        assert rs.client_id == "c1"
        assert rs.client_name == "My App"

    def test_invalid_source_raises(self):
        with pytest.raises(ValidationError):
            RegistrationSource(source="invalid")

    def test_client_id_stripped(self):
        rs = RegistrationSource(client_id="  c1  ")
        assert rs.client_id == "c1"

    def test_client_id_empty_becomes_none(self):
        rs = RegistrationSource(client_id="  ")
        assert rs.client_id is None

    def test_client_id_too_long_raises(self):
        with pytest.raises(ValidationError, match="255"):
            RegistrationSource(client_id="x" * 256)

    def test_client_name_stripped(self):
        rs = RegistrationSource(client_name="  App  ")
        assert rs.client_name == "App"

    def test_client_name_empty_becomes_none(self):
        rs = RegistrationSource(client_name="")
        assert rs.client_name is None

    def test_client_name_too_long_raises(self):
        with pytest.raises(ValidationError, match="255"):
            RegistrationSource(client_name="x" * 256)


# ---------------------------------------------------------------------------
# RegisterRequest — password validation
# ---------------------------------------------------------------------------


class TestRegisterRequestPassword:
    def _make(self, password):
        return RegisterRequest(
            email="test@example.com",
            password=password,
            profile=VALID_PROFILE,
        )

    def test_valid_password(self):
        r = self._make(VALID_PASSWORD)
        assert r.password == VALID_PASSWORD

    def test_too_short_raises(self):
        with pytest.raises(ValidationError, match="8"):
            self._make("P@ss1")

    def test_too_long_raises(self):
        with pytest.raises(ValidationError, match="128"):
            self._make("P@ssw0rd!" + "a" * 121)

    def test_no_lowercase_raises(self):
        with pytest.raises(ValidationError, match="lowercase"):
            self._make("P@SSW0RD!")

    def test_no_uppercase_raises(self):
        with pytest.raises(ValidationError, match="uppercase"):
            self._make("p@ssw0rd!")

    def test_no_digit_raises(self):
        with pytest.raises(ValidationError, match="digit"):
            self._make("P@sswOrd!")

    def test_no_special_char_raises(self):
        with pytest.raises(ValidationError, match="special"):
            self._make("Passw0rdd")


# ---------------------------------------------------------------------------
# RegisterRequest — other fields
# ---------------------------------------------------------------------------


class TestRegisterRequest:
    def test_valid_full(self):
        r = RegisterRequest(
            email="test@example.com",
            password=VALID_PASSWORD,
            profile=VALID_PROFILE,
            registration_source={"source": "direct"},
        )
        assert r.email == "test@example.com"
        assert r.registration_source.source == "direct"

    def test_invalid_email_raises(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="not-an-email",
                password=VALID_PASSWORD,
                profile=VALID_PROFILE,
            )

    def test_no_registration_source(self):
        r = RegisterRequest(
            email="test@example.com",
            password=VALID_PASSWORD,
            profile=VALID_PROFILE,
        )
        assert r.registration_source is None


# ---------------------------------------------------------------------------
# RegisterResponse
# ---------------------------------------------------------------------------


class TestRegisterResponse:
    def test_valid(self):
        r = RegisterResponse(id="123", email="test@example.com", message="OK")
        assert r.id == "123"
        assert r.email == "test@example.com"
        assert r.message == "OK"

    def test_missing_field_raises(self):
        with pytest.raises(ValidationError):
            RegisterResponse(id="123", email="test@example.com")


class TestRegistrationSourceExplicitNone:
    def test_explicit_none_client_id_stays_none(self):
        rs = RegistrationSource(client_id=None, client_name=None)

        assert rs.client_id is None
        assert rs.client_name is None
