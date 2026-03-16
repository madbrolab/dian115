__all__ = ["AliyunPanLogin", "BAligo"]


from typing import List, Dict, Optional
from pathlib import Path

import httpx
from orjson import loads
from aligo import Aligo, BatchRequest, BatchSubRequest


class AliyunPanLogin:
    """
    阿里云盘登入
    """

    @staticmethod
    def qr() -> Dict:
        """
        qr 获取
        """
        url = "https://passport.aliyundrive.com/newlogin/qrcode/generate.do"
        params = {
            "appName": "aliyun_drive",
            "fromSite": "52",
            "appEntrance": "web",
            "_csrf_token": "",
            "umidToken": "",
            "isMobile": "false",
            "lang": "zh_CN",
            "returnUrl": "",
            "hsiz": "",
            "bizParams": "",
            "_bx-v": "2.0.31",
        }

        try:
            res = httpx.get(url, params=params, timeout=10, follow_redirects=True)
            res.raise_for_status()
            return res.json()
        except httpx.RequestError as e:
            return {"error": str(e)}

    @staticmethod
    def ck(t, ck) -> Dict:
        """
        ck 获取
        """
        try:
            url = "https://passport.aliyundrive.com/newlogin/qrcode/query.do?appName=aliyun_drive&fromSite=52&_bx-v=2.0.31"
            form_data = {
                "t": t,
                "ck": ck,
                "ua": "140#ApzoT1O+zzPDRQo245+u33Sc2qq3vOsx37btKgtYp/+IQTwpilmRWL7UklKiXOSxEgmrlBPw4oOKU3hqzzngEzCNOa+xzWz8ijlulFzx2DD3VthqzFHcHbzum51xxD2iVP//lbzx2dfHKCUI1wba7XElyb98FLkGcBq9NLTwSgAzL+yICWq/l5WrYJ+B3qlPPFJg+BxuOJkpm+kszeUq29TiOuclegGQGrpKbFQOPCQE+u94nT7aL8G9Aq84NbL7nhfeFD9BpnzRPrEJrbCbpA3Kk7IsEW3gDIgSC4pQVKuM1VwwGaIuNdotnVtfuCceOFxWedDGMKHlr9NLAu9JKzRJBASFHRNdObSUeSklxZdXIHnupibAkG9mTwAEtajstVuX75Y7icOS5KhgQFP7iNuqEEeARX3DiMkI0pDw0Ybj5Q5JrXCz9AL6CTW3t0Zw5lE68UmECpi1eMwuY46BXykk4ET7+Jm7a+RVUTnWP5vfFV0omNauBNpsVggw/MYMxy4czMfMRiQwglJGBIVw+Mr18S+BAvJzqaUXg+HDUphISFsirUND0/u3zg+FM06Zc6rsVmxE2eSffE3cpgfVYoN/Hf24yFJCOVnVlIEagQF2CPxBQIDL+Q9E/f1l3lfQktqrC0GgxdPNv5ifjzp9IDb3t4h75O2daoJDnKcYhDfbKFvpqUgwkUCzzYspDRPv4XXAhsNq6KQZr3nP1AKdSjEL4XQSAGh4HCE1zHrvKPz93BYl68ZHZig9975vH+/fQlgzMRQE3NRaPBSh1a2If53LnMFj6f1g5OH1ZEPIZBq+K6RSGs6RJJ8NRKibX8weXQEXwVar9UeBKxIwGPW4Nysitb9/Le2NYpEf0oKIrGB/T0AEyieR1BNv8M8pNDIJ9M/lPDyoN4kB5sxD0E+=",  # noqa: E501
                "appName": "aliyun_drive",
                "appEntrance": "web",
                "_csrf_token": "uJPMkz6XudG40RXo6xCuW5",
                "umidToken": "6795f5c4caafbf6e9623941b8a3056b3e318c1fd",
                "isMobile": "false",
                "lang": "zh_CN",
                "returnUrl": "",
                "hsiz": "10918f04a35e8c83cf032e462eb88647",
                "fromSite": "52",
                "bizParams": "",
                "navlanguage": "zh-CN",
                "navUserAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",  # noqa: E501
                "navPlatform": "Win32",
            }
            headers = {
                "origin": "https://passport.aliyundrive.com",
                "referer": "https://passport.aliyundrive.com/mini_login.htm?&appName=aliyun_drive",
            }

            res = httpx.post(url, data=form_data, headers=headers, timeout=10, follow_redirects=True)
            res.raise_for_status()

            return res.json()

        except Exception as err:  # pylint: disable=W0718
            return {"error": str(err)}

    @staticmethod
    def get_token(path: Path) -> Optional[str]:
        """
        获取 Aligo Token
        """
        if not path.exists():
            return None
        with open(path, "rb") as file:
            data = loads(file.read())
            aligo_refresh_token = data.get("refresh_token")
            if aligo_refresh_token:
                return aligo_refresh_token
        return None


class BAligo(Aligo):
    """
    增加批量删除文件功能
    """

    V3_FILE_DELETE = "/v3/file/delete"

    def delete_file(self, file_id: str, drive_id: str = None) -> bool:
        """
        删除文件
        """
        drive_id = drive_id or self.default_drive_id
        response = self.post(
            self.V3_FILE_DELETE, body={"drive_id": drive_id, "file_id": file_id}
        )
        return response.status_code == 204

    def batch_delete_files(self, file_id_list: List[str], drive_id: str = None) -> List:
        """
        批量删除文件
        """
        drive_id = drive_id or self.default_drive_id
        result = self.batch_request(
            BatchRequest(
                requests=[
                    BatchSubRequest(
                        id=file_id,
                        url="/file/delete",
                        body={"drive_id": drive_id, "file_id": file_id},
                    )
                    for file_id in file_id_list
                ]
            ),
            dict,
        )
        return list(result)
