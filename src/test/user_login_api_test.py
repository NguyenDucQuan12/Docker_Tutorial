import requests

# Địa chỉ api lấy token
url_get_token = "http://172.31.99.130:8000/auth/login"

data = {
    "username": "nguyenducquan2001@gmail.com",
    "password": "1"
}

# Gọi api lấy token, tham số được truyền qua body với đối tượng là data
response = requests.post(
    url= url_get_token,
    data= data
)
my_token = response.json().get("access_token")

# print(my_token)

# Địa chỉ URL của API cần gọi
url = "http://172.31.99.130:8000/user_login/activate_user/{email_user}"

# Thông tin cần truyền vào (email_user và activate)
email_user = "tvc_adm_it@terumo.co.jp"
activate = True  # Hoặc False để hủy kích hoạt

# Dữ liệu truyền vào dưới dạng tham số query
params = {"activate": activate}

# Thêm headers( token xác thực)
headers = {
    "Authorization": f"Bearer {my_token}"
}

# Gọi API vs tham số truyền vào là params (là các tham số truyền vào url như: http://172.31.99.130:8000/user_login/activate_user/tvc_adm_it%40terumo.co.jp?activate=true')
response = requests.put(
    url = url.format(email_user=email_user),
    params= params,
    headers= headers
)

# Kiểm tra kết quả
if response.status_code == 200:
    print("API call successful!")
    print(response.json())  # Hiển thị kết quả trả về từ API
else:
    print(f"API call failed with status code {response.status_code}")
    print(response.text)  # Hiển thị chi tiết lỗi nếu có
