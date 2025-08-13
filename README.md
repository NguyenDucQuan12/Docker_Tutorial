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

### 2.3 Thực hiện truy vấn CSDL

Đối với các câu lệnh truy vấn tới CSDL, ta phân chia các câu lệnh thành các tệp truy vấn tương ứng với từng bảng. Ví dụ với bảng `User_Login` ta thực hiện tất cả các câu truy vấn tại tệp [db_user_login](src/db/db_user_login.py).  

Tại đây khi ta yêu cầu người dùng cung cấp các thông tin, ta có thể sử dụng các lược đồ đã tạo trước đó để người dùng có thể nhập thông tin tốt hơn, tránh nhập các thông tin ngoài lược đồ.  

```python
from schemas.schemas import User_Login_Base

def create_new_user_login(db: Session, request: User_Login_Base):

    """
    Tạo thông tin người đăng nhập mới và mã hóa mật khẩu trước khi lưu vào CSDL  
    - `request`: Thông tin mà người dùng cần cung cấp  

    Kết quả trả về:  
    200:  
    - `new_user_login`: Thông tin người dùng mới  
    500:  
    - `"message": "Lỗi khi thêm người dùng mới"`
    """
    # Tạo id cho một người
    new_user_id = get_random_string(32)
    
    # Khai báo các thông tin cho người dùng mới
    new_user_login =  DbUser_Login(
        ID = new_user_id, 
        User_Name = request.User_Name,
        Email = request.Email ,
        Password = Hash.bcrypt(request.Password), # mã hóa mật khẩu
        Avatar = DEFAULT_AVATAR,
        Privilege = DEFAULT_PRIVILEGE
    )

    # Tiến hành ghi dữ liệu
    try:
        db.add(new_user_login)
        db.commit()
        # refresh giúp nhận được giá trị ID của người dùng, vì nó là giá trị tự tăng
        db.refresh(new_user_login)

    except exc.SQLAlchemyError as e:   
        # Trong quá trình insert lỗi thì giá trị id (cột IDENTITY) vẫn tự tăng, đây là hành vi mặc định của SQL Server
        # Rollback lại giao dịch
        db.rollback()
        # Trả về lỗi
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": f"Lỗi khi thêm người dùng {request.User_Name}: {str(e)}"
            }
        )
    
    return new_user_login 
```
Ta truyền lược đồ vào câu lệnh tạo tài khoản mới: `request: User_Login_Base`. Khi đó tham số `request` sẽ tuân thủ theo lược đồ mà ta đã khai báo, và ta có thể truy vấn các thông tin cụ thể từ lược đồ thông qua thuộc tính trong nó: `request.User_Name`, ... Như vậy ta sẽ lấy các thông tin mà chúng ta muốn, nếu người dùng nhập nhiều hơn các trường thì ta cũng chỉ lấy các giá trị cụ thể bằng lược đồ.  