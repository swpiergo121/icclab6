#!/usr/bin/env python3

TEMPLATES = {
    "base.html": """<!doctype html>
<html>
<head>
  <title>User Admin</title>
  <style>
    body { font-family: sans-serif; max-width: 960px; margin: auto; padding: 20px; }
    table { border-collapse: collapse; width: 100%; }
    td, th { border: 1px solid #ccc; padding: 6px; text-align: left; }
    .flash { padding: 8px; margin: 6px 0; border-radius: 4px; }
    .error { background: #fdd; }
    .success { background: #dfd; }
    img.avatar { width: 80px; height: 80px; object-fit: cover; border-radius: 50%; }
    input { padding: 5px; margin: 3px 0; }
    button { padding: 5px 12px; cursor: pointer; }
  </style>
</head>
<body>
  <nav>
    {% if current_user.is_authenticated %}
      <a href="{{ url_for('list_users') }}">Users</a> |
      <a href="{{ url_for('new_user') }}">New user</a> |
      <a href="{{ url_for('profile') }}">My profile</a> |
      <a href="{{ url_for('logout') }}">Logout ({{ current_user.username }})</a>
    {% endif %}
  </nav>
  <hr>
  {% with msgs = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in msgs %}<div class="flash {{ cat }}">{{ msg }}</div>{% endfor %}
  {% endwith %}
  {% block content %}{% endblock %}
</body>
</html>""",

    "login.html": """{% extends "base.html" %}
{% block content %}
<h2>Admin login</h2>
<form method="post">
  <p><input name="username" placeholder="Username" required></p>
  <p><input name="password" type="password" placeholder="Password" required></p>
  <button type="submit">Login</button>
</form>
{% endblock %}""",

    "users.html": """{% extends "base.html" %}
{% block content %}
<h2>Users</h2>
<form method="get">
  <input name="q" value="{{ q }}" placeholder="Search username or email">
  <button type="submit">Search</button>
</form>
<table>
  <tr><th>ID</th><th>Photo</th><th>Username</th><th>Email</th><th>Admin</th><th>Actions</th></tr>
  {% for u in users %}
  <tr>
    <td>{{ u.id }}</td>
    <td>{% if u.image_key %}<img class="avatar" src="{{ image_url(u.image_key) }}" width="40" height="40">{% endif %}</td>
    <td>{{ u.username }}</td>
    <td>{{ u.email }}</td>
    <td>{{ 'Yes' if u.is_admin else 'No' }}</td>
    <td>
      <a href="{{ url_for('user_detail', user_id=u.id) }}">View</a> |
      <a href="{{ url_for('edit_user', user_id=u.id) }}">Edit</a> |
      <form method="post" action="{{ url_for('delete_user', user_id=u.id) }}" style="display:inline"
            onsubmit="return confirm('Delete this user?');">
        <button type="submit">Delete</button>
      </form>
    </td>
  </tr>
  {% else %}
  <tr><td colspan="6">No users found.</td></tr>
  {% endfor %}
</table>
{% endblock %}""",

    "user_form.html": """{% extends "base.html" %}
{% block content %}
<h2>{{ title }}</h2>
<form method="post" enctype="multipart/form-data">
  <p>Username<br><input name="username" value="{{ user.username or '' }}" required></p>
  <p>Email<br><input name="email" type="email" value="{{ user.email or '' }}" required></p>
  <p>Password {% if user.id %}(leave blank to keep current){% endif %}<br>
     <input name="password" type="password" minlength="8" {% if not user.id %}required{% endif %}></p>
  {% if not profile %}
  <p><label><input type="checkbox" name="is_admin" {% if user.is_admin %}checked{% endif %}> Admin</label></p>
  {% endif %}
  {% if user.image_key %}<p><img class="avatar" src="{{ image_url(user.image_key) }}" style="width:150px;height:150px;"></p>{% endif %}
  <p>Photo (png, jpg, jpeg, gif, webp; max 5 MB)<br><input type="file" name="image" accept="image/*"></p>
  <button type="submit">Save</button>
</form>
{% endblock %}""",

    "user_detail.html": """{% extends "base.html" %}
{% block content %}
<h2>{{ user.username }}</h2>
{% if user.image_key %}
  <img class="avatar" src="{{ image_url(user.image_key) }}" style="width:200px;height:200px;">
{% endif %}
<table>
  <tr><th>ID</th><td>{{ user.id }}</td></tr>
  <tr><th>Email</th><td>{{ user.email }}</td></tr>
  <tr><th>Admin</th><td>{{ 'Yes' if user.is_admin else 'No' }}</td></tr>
  <tr><th>Created</th><td>{{ user.created_at }}</td></tr>
</table>
<p>
  <a href="{{ url_for('edit_user', user_id=user.id) }}">Edit</a> |
  <a href="{{ url_for('list_users') }}">Back to list</a>
</p>
{% endblock %}""",
}
