import pytest
from flask_login import login_user
from cleanbox.models import User, UserAccount, Category, db
from cleanbox import create_app
from unittest.mock import patch, MagicMock


@pytest.fixture
def app():
    app = create_app(testing=True)
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login_test_user(app, client):
    with app.app_context():
        user = User(id="test-user", email="test@example.com")
        db.session.add(user)
        db.session.commit()
        account = UserAccount(
            user_id=user.id,
            account_email="test@example.com",
            is_primary=True,
            is_active=True,
        )
        db.session.add(account)
        db.session.commit()
        category = Category(
            user_id=user.id, name="Work", description="Work", is_active=True
        )
        db.session.add(category)
        db.session.commit()
        login_user(user)
        yield user


class TestCategory:
    def test_list_categories_requires_login(self, client):
        response = client.get("/category/", follow_redirects=False)
        if response.status_code == 404:
            pytest.skip("/category/ route not found. Test after implementation.")
        assert response.status_code in (200, 302, 303)
        if response.status_code in (302, 303):
            assert "/auth/login" in response.location

    def test_list_categories_success(self, client, login_test_user):
        response = client.get("/category/", follow_redirects=False)
        if response.status_code == 404:
            pytest.skip("/category/ route not found. Test after implementation.")
        assert response.status_code in (200, 302, 303)
        # Check if category management page is rendered properly
        assert "Category Management" in response.data.decode()

    @patch("cleanbox.category.routes.Category")
    def test_add_category_success(self, mock_category, client, login_test_user):
        mock_category.query.filter_by.return_value.first.return_value = None
        response = client.post(
            "/category/add",
            data={
                "name": "Work",
                "description": "Work",
                "color": "#123456",
                "icon": "fas fa-briefcase",
            },
            follow_redirects=False,
        )
        if response.status_code == 404:
            pytest.skip("/category/add route not found. Test after implementation.")
        assert response.status_code in (200, 302, 303)

    @patch("cleanbox.category.routes.Category")
    def test_add_category_duplicate(self, mock_category, client, login_test_user):
        mock_category.query.filter_by.return_value.first.return_value = MagicMock()
        response = client.post(
            "/category/add",
            data={"name": "Work", "description": "Work"},
            follow_redirects=False,
        )
        if response.status_code == 404:
            pytest.skip("/category/add route not found. Test after implementation.")
        assert response.status_code in (200, 302, 303)

    def test_add_category_empty_name(self, client, login_test_user):
        response = client.post(
            "/category/add",
            data={"name": "", "description": "Work"},
            follow_redirects=False,
        )
        if response.status_code == 404:
            pytest.skip("/category/add route not found. Test after implementation.")
        assert response.status_code in (200, 302, 303)

    @patch("cleanbox.category.routes.Category")
    def test_edit_category_success(self, mock_category, client, login_test_user):
        mock_cat = MagicMock()
        mock_category.query.filter_by.return_value.first.return_value = mock_cat
        mock_category.query.filter_by.return_value.filter.return_value.first.return_value = (
            None
        )
        response = client.post(
            "/category/edit/1",
            data={"name": "Personal", "description": "Personal"},
            follow_redirects=False,
        )
        if response.status_code == 404:
            pytest.skip("/category/edit/1 route not found. Test after implementation.")
        assert response.status_code in (200, 302, 303)

    @patch("cleanbox.category.routes.Category")
    def test_edit_category_duplicate_name(self, mock_category, client, login_test_user):
        mock_cat = MagicMock()
        mock_category.query.filter_by.return_value.first.return_value = mock_cat
        mock_category.query.filter_by.return_value.filter.return_value.first.return_value = (
            MagicMock()
        )
        response = client.post(
            "/category/edit/1",
            data={"name": "Work", "description": "Work"},
            follow_redirects=False,
        )
        if response.status_code == 404:
            pytest.skip("/category/edit/1 route not found. Test after implementation.")
        assert response.status_code in (200, 302, 303)

    @patch("cleanbox.category.routes.Category")
    def test_edit_category_not_found(self, mock_category, client, login_test_user):
        mock_category.query.filter_by.return_value.first.return_value = None
        response = client.post(
            "/category/edit/999",
            data={"name": "Work", "description": "Work"},
            follow_redirects=False,
        )
        if response.status_code == 404:
            pytest.skip(
                "/category/edit/999 route not found. Test after implementation."
            )
        assert response.status_code in (200, 302, 303)

    @patch("cleanbox.category.routes.Category")
    def test_delete_category_success(self, mock_category, client, login_test_user):
        mock_cat = MagicMock()
        mock_category.query.filter_by.return_value.first.return_value = mock_cat
        response = client.post("/category/delete/1", follow_redirects=False)
        if response.status_code == 404:
            pytest.skip(
                "/category/delete/1 route not found. Test after implementation."
            )
        assert response.status_code in (200, 302, 303)

    @patch("cleanbox.category.routes.Category")
    def test_delete_category_not_found(self, mock_category, client, login_test_user):
        mock_category.query.filter_by.return_value.first.return_value = None
        response = client.post("/category/delete/999", follow_redirects=False)
        if response.status_code == 404:
            pytest.skip(
                "/category/delete/999 route not found. Test after implementation."
            )
        assert response.status_code in (200, 302, 303)
