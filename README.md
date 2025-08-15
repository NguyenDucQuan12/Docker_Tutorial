> [!NOTE]  
> ### Hướng dẫn sử dụng docker

# I.Docker Desktop

## 1. Cài đặt Docker Desktop
Đầu tiên ta cần tải và cài đặt `Docker Desktop` từ trang chủ của `Docker` [tại đây](https://www.docker.com/)  

![image](assets/github_img/docker_home.png)

Khi tải về cho máy tính thì sẽ cho ra tệp tin `Docker Desktop Installer` và ta khởi chạy tệp tin bằng cách click 2 lần vào tệp đó.  

![image](assets/github_img/docker_desktop_installer.png)

Thêm các hình ảnh cài docker vào các bước phía dưới


## 2. Một số lỗi khi cài đặt
Dưới đây là một số lỗi xảy ra trong quá trình cài đặt `Docker Desktop`  

# II. Xây dựng phần mềm chạy với Docker  

## 1. Xây dựng phần mềm
Để có thể chạy với `Docker` thì tất nhiên ta phải có phần mềm trước. Dưới đây là hướng dẫn ví dụ với phần mềm sử dụng `Python 3.10`, `Fast API`.  

Cấu trúc dự án như sau:  
```
Docker/
│
├── src/
│   ├── main.py           # Tệp chính chạy chương trình
│   ├── api/              # Các router (endpoint)
│   │   ├── __init__.py
│   │   └── example.py
│   ├── schemas/                # Các schema để validation dữ liệu
│   │   ├── __init__.py
│   │   ├── user.py             # Schema cho User
│   │   └── item.py   
│   ├── services/         # Các dịch vụ khác
│   │   ├── __init__.py
│   │   ├── user_service.py
|   |   └── mail_service.py
│   ├── db/               # Kết nối database
│   |   ├── __init__.py
│   |   └── session.py
|   └──utils/
|       ├── __init__.py
|       ├── hash.py
|       └── token.py
│
├── requirements.txt      # Danh sách package cần cài
├── Dockerfile            # Nếu cần chạy bằng Docker
└── README.md
```

## 2. Xây dựng CSDL
Sử dụng `sqlalchemy` và `pydantic` để kết nối với `SQL Server`.  

```python
# Cài đặt SQLAlchemy để kết nối với SQL Server
pip install sqlalchemy

# Cài đặt Pydantic để sử dụng cho validation
pip install pydantic
```

Tạo kết nối với CSDL thông qua chuỗi kết nối được lấy từ biến môi trường (tệp .env):  

```python
# Cấu trúc chuỗi kết nối đến SQL Server
connection_url = URL.create(
    "mssql+pyodbc",
    username = os.getenv("DB_USER"), # Tên đăng nhập 
    password = os.getenv("DB_PASSWORD"), # mật khẩu đăng nhập
    host = os.getenv("DB_HOST") or "host.docker.internal" , # Địa chỉ IP của máy tính lấy được
    port = 1433, # cổng kết nối khi mở kết nối SQL server, xem them wor video youtube của bản thân
    database = os.getenv("DB_NAME"), # Tên của database cần truy cập
    query = {
        "driver": "ODBC Driver 18 for SQL Server", # Phiên bản driver của ODBC đã tải về từ microsoft
        "TrustServerCertificate": "yes"  
    },
)
```
Khi chạy trên `Docker` ta có thể lấy `SQL Server` tại host bằng chuỗi: `host.docker.internal`. Chuỗi này tương tự `localhost`.  
Chi tiết xem tại tệp [database](src/db/database.py)  

### 2.1 Tạo bảng trong CSDL
Lấy ví dụ với bảng `User_Login` trong CSDL.  

Đầu tiên cần định nghĩa bảng `User_Login` trong tệp [model](src/db/models.py):  
Các cột trong bảng `User_Login` được khai báo như bên dưới.  
```python
class DbUser_Login(Base):
    """
    Định nghĩa bảng thông tin đăng nhập   
    Mật khẩu đã được mã hóa trước khi lưu vào CSDL  
    """
    __tablename__ = "Users_Login"
    ID = Column(Unicode(200), primary_key=True)
    User_Name = Column(Unicode(500)) # Sử dụng kiểu Nvarchar: NVARCHAR
    Email = Column(Unicode(200), unique=True) # Không được trùng nhau
    Password = Column(Unicode(200))
    Avatar = Column(Unicode(400))
    Privilege = Column(Unicode(100))
    Activate = Column(DateTime)
    OTP_Code = Column(Unicode(100))
    Expiration_Time = Column(DateTime)
    Status = Column(Unicode(500))
```
Với 1 bảng được sử dụng trong SQLAchemy thì luôn yêu cầu `khóa chính`, vì vậy ta khai báo cột `ID` làm khóa chính.  

### 2.2 Tạo lược đồ cho bảng

Sau khi khai báo bảng `User_Login` ta sẽ tiến hành tạo các lược đồ `lấy thông tin từ người dùng` và lược đồ `trả về các thông tin cho người dùng`.  
Ví dụ với bảng `User_Login` có 10 cột, tuy nhiên khi đăng ký tài khoản mới ta chỉ cần người dùng cung cấp: `User_Name`,`Email`, `Password` và có thể thêm giá trị `ID` hoặc để `ID` là giá trị sinh ra random thì ko cần người dùng cung cấp.  
Còn khi ta hiển thị thông tin cho người dùng thì cũng chỉ hiển thị một số thông tin hạn chế, không nên hiển thị toàn bộ thông tin. Như khi người dùng đăng ký mới, người dùng cung cấp mật khẩu để đăng ký, tuy nhiên khi đăng ký thành công ta chỉ trả về cho người dùng `Họ tên`, `Email` của họ. Còn mật khẩu của họ thì chúng ta đã mã hóa, không trả về mật khẩu của họ.  

Vì vậy ta cần tạo ra các lược đồ tương ứng với mỗi yêu cầu tại tệp [schemas](src/schemas/schemas.py):  
```python
class User_Login_Base(BaseModel):
    """
    Class này chứa thông tin cần được cung cấp để tạo một thông tin đăng nhập mới
    - **ID**: Mã cho mỗi người đăng nhập
    - **User_Name**: Họ tên người đăng nhập 
    - **Email**: Email của người đăng nhập
    - **Password**: Mật khẩu người đăng nhập
    - **Avatar**: Đường dẫn tới hình ảnh người đăng nhập 
    - **Privilege**: Quyền hạn  
    """
    User_Name: str
    Email: str
    Password: str

class User_Login_Display(BaseModel):
    """
    Trả về thông tin người dùng theo ý muốn, không trả về những thông tin quan trọng như password đã hash
    Lưu ý tên của các trường thông tin trả về phải giống nhau, nếu không gặp lỗi
    -  **Config**: cho phép tự động chuyển đổi dữ liệu giữa CSDL (nvarchar) và kiểu mà ta đã khai báo (str)
    """
    User_Name: str
    Email: str
    Avatar:str
    Privilege: str
    class Config():
        from_attributes  = True
```

Ta có 2 lược đồ lấy thông tin người dùng và trả thông tin người dùng khi họ đăng ký tài khoản mới.  
Tùy vào nhu cầu mà có thể có nhiều lược đồ. Với các yêu cầu cần hiển thị các trường thông tin chi tiết hơn ta tạo 1 lược đồ hiển thị đầy đủ các thông tin cho người dùng như sau:  
```python
class User_Login_Full_Display(BaseModel):
    """
    Trả về đầy đủ các thông tin từ người dùng
    """
    ID = str
    User_Name = str
    Email = str
    Password = str
    Avatar = str
    Privilege = str
    Activate = datetime
    OTP_Code = str
    Expiration_Time = datetime
    Status = str
    class Config():
        from_attributes = True

class User_Login_OTP_Display (BaseModel):
    """
    Trả về các thông tin khi người dùng truy vấn mã OTP
    """
    ID = str
    User_Name = str
    Email = str
    OTP_Code = str
    Expiration_Time = datetime
```

> Các tên trong lược đồ và kết quả trả về phải trùng khớp với nhau (phân biệt chữ hoa chữ thường)  
> Như vậy thì lược đồ mới tự động chọn lọc các thông tin trùng nhau, bỏ các thông tin không cần thêm vào lược đồ  
> Đối với các dữ liệu trả về từ Databse thì tốt nhất nên đặt tên các trường trong lược đồ trùng tên với các cột trong Database  

### 2.3 Thực hiện truy vấn CSDL

Đối với các câu lệnh truy vấn tới CSDL, ta phân chia các câu lệnh thành các tệp truy vấn tương ứng với từng bảng. Ví dụ với bảng `User_Login` ta thực hiện tất cả các câu truy vấn tại tệp [db_user_login](src/db/db_user_login.py).  

Tại đây khi ta yêu cầu người dùng cung cấp các thông tin, ta có thể sử dụng các lược đồ đã tạo trước đó để người dùng có thể nhập thông tin tốt hơn, tránh nhập các thông tin ngoài lược đồ.  

```python
def create_new_user_login(db: Session, new_user_login: DbUser_Login):

    """
    Tạo người dùng mới vào CSDL
    - `new_user_login`: Thông tin người dùng mới cần thêm vào CSDL  
    """
    # Cú pháp trả về khi gọi CSDL
    response = {
        "success": False,
        "data": None,
        "message": "Lỗi khi thêm người dùng mới"
    }

    # Tiến hành ghi dữ liệu
    try:
        db.add(new_user_login)
        db.commit()
        # refresh giúp nhận được giá trị ID của người dùng, vì nó là giá trị tự tăng
        db.refresh(new_user_login)

        # Trả về kết quả thành công
        response["message"] = "Thêm người dùng mới thành công"
        response["success"] = True
        response["data"] = new_user_login

    except exc.IntegrityError as e:  # Bắt lỗi vi phạm ràng buộc (ví dụ: khóa chính, khóa ngoại)
        db.rollback()
        response["message"] = f"Lỗi khi thêm người dùng mới: Vi phạm ràng buộc dữ liệu ({str(e)})"
    
    except exc.DataError as e:  # Bắt lỗi kiểu dữ liệu không hợp lệ (ví dụ: vượt quá độ dài chuỗi, kiểu dữ liệu sai)
        db.rollback()
        response["message"] = f"Lỗi khi thêm người dùng mới: Lỗi dữ liệu ({str(e)})"
    
    except exc.SQLAlchemyError as e:  # Bắt tất cả các lỗi khác từ SQLAlchemy
        db.rollback()
        response["message"] = f"Lỗi khi thêm người dùng mới: {str(e)}"
    
    except Exception as e:  # Bắt tất cả các lỗi ngoài SQLAlchemy
        db.rollback()
        response["message"] = f"Lỗi không xác định: {str(e)}"        
    
    return response 
```
Luôn chạy các câu lệnh thao tác với CSDL vào khối `try-except` để xử lý tốt các trường hợp lỗi xảy ra.  

## 3.Tạo endpoint cho các api

Đối với mỗi api ta sẽ để vào thư mục [api](src/api), ví dụ với api: `user_login` có thể tham khảo tại tệp [user_login](src/api/user_login.py).  
Ta đặt tên tệp trùng với endpoint để tạo sự đồng nhất, dễ nhận biết và sửa lỗi sau này.  
Với mỗi endpoint ta cần khai báo tiền tố của endpoint đó.  
```python
# Khai báo router với tiền tố cho các endpoint là: /user_login/xxx
router = APIRouter(
    prefix = "/user_login",
    tags= ["User Login"]
)
```
Mặc định các endpoint sẽ được tự động thêm tiền tố `prefix` vào đầu các địa chỉ. Ví dụ: `http://172.31.99.130:8000/user_login/abc_enpoint`  

### 3.1 Các enpoint không cần xác thực người dùng (Non Authentication)
Với mỗi endpoint ta khai báo như sau:  
```python
@router.post("/new_user", response_model = User_Login_Display)
def create_user(request: User_Login_Base, db: Session = Depends(get_db)):
    """
    Tạo thông tin người dùng vào CSDL
    """
    return User_Login_Controller.create_user(db= db, request= request)
```
Đầu tiên cần nhận định phương thức của endponit này là thuộc các phương thức sau:  
- `get`: Lấy dữ liệu từ máy chủ và trả về  
- `put`: Ghi đè dữ liệu được gửi từ client lên máy chủ  
- `post`: Gửi thông tin tới máy chủ, thường là biểu mẫu dùng để đăng ký mới  
- `delete`: Xóa tài nguyên trên máy chủ  

Khi 1 api được khai báo với phương thức là `post` nhưng khi bạn sử dụng nó với phương thức khác như `get`, `delete`, ... thì sẽ nhận được lỗi `405 (Method not allowed)`.  

Sau đó tạo đường dẫn cho router này bằng 2 loại:  
- Tham số không nằm trong đường dẫn: là đường dẫn chỉ chứa các hằng số, ko chứa các biến  
Ví dụ: `"/new_user"`, `"/check_user/my_db"`, ...  
- Tham số nằm trong đường dẫn: Là đường dẫn mà trong đó chứa các tham số được người dùng truyền vào  
Ví dụ: `"/activate_user/{email_user}"`, `"/get_user/{department}"`, ...  

Ta có thể thêm tùy chọn `response_mode` là kiểu trả về cho người dùng. Khi ta muốn giới hạn tham số trả về cho người dùng, ẩn đi các tham số nhạy cảm như mật khẩu, token,... thì ta có thể sử dụng kiểu trả về như này, router mặc định chỉ giữa lại các tham số giống với lược đồ đã khai báo.  
Tham số của `response_mode` là một lược đồ đã được khai báo ở [schemas](src/schemas/schemas.py) và đã hướng dẫn chi tiết phía trên. Còn nếu không thêm tham số trả về này thì mặc định khi router trả về bất cứ cái gì thì nó sẽ giữ nguyên như vậy.  

Sau khi đã tạo router, ta tạo hàm xử lý cho router đó, mỗi khi có người gọi vào api thì hàm xử lý sẽ được chạy và trả về kết quả mong muốn.  
```python
def create_user(request: User_Login_Base, db: Session = Depends(get_db)):
```
Endpoint `/user_login/new_user` sẽ gọi hàm `create_user` với các tham số yêu cầu như sau:  
- `request`: tham số này tuân thủ theo lược đồ `User_Login_Base`  
- `db`: tham số này tuân thủ theo yêu cầu `Session` của Database và có hàm phụ thuộc `Depends(get_db)`. Hàm `Depends` có ý nghĩa là sẽ gọi hàm `get_db` trước khi chạy vào hàm `create_user` nhằm mục đích tạo kết nối tới CSDL trước khi chạy các câu lệnh khác.  

Sau đó hàm `create_user` gọi tới controller kiểm soát các hành vi của endpoint này.  

### 3.2 Các endpoint cần xác thực người dùng (Authentication)

Với một số endpoint bảo mật, không thể tùy ý cho bất cứ ai cũng sử dụng được. Ta cần xác thực người dùng, xem họ có quyền sử dụng api này hay không. Ví dụ với các thao tác như xóa dữ liệu, thay đổi dữ liệu ta nên hạn chế việc ai cũng có thể sử dụng api này. Vì vậy ta tạo ra một phương thức xác thực trước khi cho họ thao tác với api.  

Một api có xác thực người dùng được khai báo như sau:  
```python
@router.delete("/delete_user/{email_user}")
def delete_user(email_user: str, db: Session = Depends(get_db), current_user : UserAuth = Depends(get_info_user_via_token)):
    """
    Xóa tài khoản người dùng
    - `email_user`: Email của người dùng cần kích hoạt hoặc hủy kích hoạt
    """    
    return User_Login_Controller.delete_user(db= db, email_user= email_user, current_user = current_user)
```

Cũng tương tự như với các endpoint không cần xác thực người dùng về phương thức, hàm, ... chỉ có sự khác biệt là với hàm gọi khi thực hiện truy vấn api ta có thêm: `current_user : UserAuth = Depends(get_info_user_via_token)`.  
Trước khi người dùng được truy cập vào api ta phải xác thực người dùng trước đã, vì vậy ta có lệnh: `Depends(get_info_user_via_token)`, lệnh này sẽ gọi hàm `get_info_user_via_token` trước khi thực hiện hàm `delete_user`.  
Hàm `get_info_user_via_token` sẽ giải mã token và lấy thông tin người dùng được đính kèm vào token gọi là `payload`. Tất cả thông tin về người dùng sẽ được lưu vào biến `current_user`. Biến này sẽ được đưa vào controller và chịu trách nhiệm phân tích, xử lý, ...  

> Cách thức tạo token và xác thực có thể xem tại tệp [auth](src/auth/oauth2.py) và [authentication](src/auth/authentication.py)  

Khi người dùng gọi api này, bắt buộc họ phải truyền vào api một tham số xác thực là `header`. `Header` này chứa token như sau:  
```python
# Địa chỉ URL của API cần gọi
url = "http://172.31.99.130:8000/user_login/delete_user/{email_user}"

# Thông tin cần truyền vào (email_user)
email_user = "nguyenducquan2001@gmail.com"

# Thêm headers( token xác thực)
headers = {
    "Authorization": f"Bearer {my_token}"
}

# Gọi API 
response = requests.put(
    url = url.format(email_user=email_user),
    headers= headers
)
```
### 3.3 Tạo controller xử lý các endpoint

Sau khi tọa endpoint và các hàm xử lý khi api được gọi, để code rõ ràng, nhìn đẹp mắt, sau này cũng dễ sửa chữa, nâng cấp thì các thao tác khi người dùng gọi api sẽ được xử lý ở một trung gian kết nối tất cả (Database, authentication, cilent, ...) là `Controller`.  

Các controller được đặt tại thư mục [controller](src/controllers). Mỗi controller sẽ được đặt tên trùng với api để dễ dàng nhận biết controller này chịu trách nhiệm xử lý cho api nào.  
Với controller của `user_login` ta có thể tham khảo tại [user_login_controller](src/controllers/user_login_controller.py)  

Khi gọi api tạo người dùng mới tại địa chỉ: ` http://172.31.99.130:8000/user_login/new_user`. Api này sẽ gọi tới hàm `create_user` và hàm `create_user` sẽ gọi tới controller để xử lý như sau:  

```python
def create_user(request: User_Login_Base, db: Session):
    """
    Tạo thông tin người dùng mới
    """
    # Tạo id ngẫu nhiên cho một người
    new_user_id = get_random_string(32)

    # Validate các thông tin người dùng mới
    if not request.User_Name or not request.Email or not request.Password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Tên người dùng, email và mật khẩu là bắt buộc"
            }
        )
    
    # Kiểm tra email là hợp lệ
    if not re.match(EMAIL_REGEX, request.Email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": f"Email {request.Email} không hợp lệ"
            }
        )
    
    # Ép các giá trị sang kiểu chuỗi
    user_name = str(request.User_Name)
    email = str (request.Email)
    password = str(request.Password)

    # Kiểm tra email đã tồn tại trên CSDL chưa
    existing_user = db_user_login.get_user_login_by_email(db= db, email= email)

    if existing_user["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": f"Email {request.Email} đã được sử dụng. Hãy lựa chọn tài khoản khác."
            }
        )
    elif existing_user["success"] is False:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": f"Xảy ra lỗi trong quá trình tạo người dùng {request.Email}: {existing_user['message']}"
            }
        )
    else:
        # Khai báo các thông tin cho người dùng mới
        new_user_login =  DbUser_Login(
            ID = new_user_id, 
            User_Name = user_name,
            Email = email,
            Password = Hash.bcrypt(password), # mã hóa mật khẩu
            Avatar = DEFAULT_AVATAR,
            Privilege = DEFAULT_PRIVILEGE
        )

        # Gọi hàm để thêm người dùng mới vào CSDL
        new_user = db_user_login.create_new_user_login(db=db, new_user_login=new_user_login)  

        # Kiểm tra kết quả trả về từ hàm tạo người dùng mới
        if not new_user["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "message": new_user["message"]
                }
            ) 

    return new_user["data"]
```

Ta nhận vào `request: User_Login_Base` là thông tin được yêu cầu người dùng nhập vào tuân theo lược đồ `User_Login_Base`.  
Khi nhận được thông tin từ người dùng, ta cần phải xác thực lại tất cả thông tin từ người dùng, bởi vì nếu không cẩn thận, người dùng đưa thông tin sai sẽ khiến cho CSDL gặp trục trặc, có thể bị tấn công, ...  
