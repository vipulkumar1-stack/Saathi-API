from typing import List

from pydantic import BaseModel


class InsuranceProduct(BaseModel):
    id: int
    name: str


class GetMasterDataData(BaseModel):
    products: List[InsuranceProduct]
